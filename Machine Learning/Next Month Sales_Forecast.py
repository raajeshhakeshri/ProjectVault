"""
Simple Sales Forecast — Auto-Aggregates Daily/Weekly/Monthly Data
---------------------------------------------------------------------
Predicts next month's sales using Linear Regression.

CSV FILE NEEDS:
- A column named "Date"
- A "Sales" column (numbers only)
- One row per day/week/month, in chronological order
"""

import os
import sys
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error
import matplotlib.pyplot as plt

# ---------------------------------------------------------
# STEP 1: Ask the user for the CSV file path, then load it
# ---------------------------------------------------------
CSV_FILE = input("Enter the path to your sales CSV file: ").strip().strip('"').strip("'")

if not os.path.isfile(CSV_FILE):
    sys.exit(f"File not found: {CSV_FILE}\nCheck the path and try again.")

raw = pd.read_csv(CSV_FILE)
print(f"\nLoaded {len(raw)} rows from {CSV_FILE}")
print(raw.head())
print()

# ----------------------------------------------------------------------
# STEP 2: Find the date column and the sales column from the loaded csv
# ----------------------------------------------------------------------
date_col_candidates = [c for c in raw.columns if c.lower() == 'date']
sales_col_candidates = [c for c in raw.columns if c.lower() in ('sales', 'revenue', 'amount', 'total')]

if not date_col_candidates:
    raise ValueError(f"Couldn't find a 'Date' column. Columns found: {list(raw.columns)}")
if not sales_col_candidates:
    raise ValueError(f"Couldn't find a sales column. Columns found: {list(raw.columns)}")

date_col = date_col_candidates[0]
sales_col = sales_col_candidates[0]

try:
    # Try common short formats first, e.g. "Jan-25" -> Jan 2025 (not day 25)
    raw[date_col] = pd.to_datetime(raw[date_col], format='%b-%y')
except (ValueError, TypeError):
    try:
        raw[date_col] = pd.to_datetime(raw[date_col], format='%B-%Y')
    except (ValueError, TypeError):
        raw[date_col] = pd.to_datetime(raw[date_col])

raw = raw.dropna(subset=[sales_col])

# -----------------------------------------------------------------
# STEP 3: Detect granularity of the data (daily / weekly / monthly)
# -----------------------------------------------------------------
raw = raw.sort_values(date_col)
gap_days = raw[date_col].diff().dt.days.dropna().median()

if gap_days <= 3:
    granularity = 'daily'
elif gap_days <= 10:
    granularity = 'weekly'
else:
    granularity = 'monthly'

print(f"Detected data granularity: {granularity} (median gap = {gap_days:.0f} days)")

# -------------------------------------------------------------------------------------------
# STEP 4: Aggregate to monthly totals for analysis (skips if already monthly data is present)
# -------------------------------------------------------------------------------------------
if granularity == 'monthly':
    monthly = raw[[date_col, sales_col]].copy()
    monthly.columns = ['Month', 'Sales']
    monthly['Month'] = monthly['Month'].dt.to_period('M').dt.to_timestamp()
else:
    monthly = (
        raw.set_index(date_col)[sales_col]
        .resample('MS')          # 'MS' = Month Start, sums everything within each month
        .sum()
        .reset_index()
    )
    monthly.columns = ['Month', 'Sales']

# Drop the most recent month if it's incomplete (common with daily/weekly data
# that doesn't end exactly on a month boundary) — avoids a misleadingly low total
last_data_date = raw[date_col].max()
last_month_start = monthly['Month'].iloc[-1]
if granularity != 'monthly':
    days_in_last_month = pd.Period(last_month_start, freq='M').days_in_month
    days_covered = (last_data_date - last_month_start).days + 1
    if days_covered < days_in_last_month * 0.9:   # less than 90% of month covered
        print(f"Dropping {last_month_start.strftime('%Y-%m')} — incomplete month "
              f"({days_covered}/{days_in_last_month} days)")
        monthly = monthly.iloc[:-1]

print(f"\nAggregated to {len(monthly)} monthly totals:")
print(monthly)
print()

if len(monthly) < 4:
    raise ValueError("Need at least 4 months of data to build a meaningful forecast.")

# ---------------------------------------------------------
# STEP 5: Convert months to numbers (1, 2, 3...)
# ---------------------------------------------------------
monthly['MonthNum'] = range(1, len(monthly) + 1)
X = monthly[['MonthNum']]
y = monthly['Sales']

# ---------------------------------------------------------
# STEP 6: Split — hold out last months to check accuracy
# ---------------------------------------------------------
test_size = min(6, len(monthly) - 2)   # never leave fewer than 2 months to train on
X_train, X_test = X[:-test_size], X[-test_size:]
y_train, y_test = y[:-test_size], y[-test_size:]

# ---------------------------------------------------------
# STEP 7: Train and check accuracy
# ---------------------------------------------------------
model = LinearRegression()
model.fit(X_train, y_train)

predictions = model.predict(X_test)
mae = mean_absolute_error(y_test, predictions)

print(f"Test check (last {test_size} month(s)):")
for actual, pred in zip(y_test, predictions):
    print(f"  Actual: {actual:.0f}   Predicted: {pred:.0f}")
print(f"\nAverage error: {mae:.0f} units")
print()

# ---------------------------------------------------------
# STEP 8: Retrain on ALL months, forecast next month
# ---------------------------------------------------------
model.fit(X, y)
next_month_num = [[len(monthly) + 1]]
next_month_df = pd.DataFrame(next_month_num, columns=['MonthNum'])
forecast = model.predict(next_month_df)[0]
next_month_label = (monthly['Month'].iloc[-1] + pd.DateOffset(months=1)).strftime('%Y-%m')
print(f"Forecast for {next_month_label}: {forecast:.0f}")

# -------------------------------------------------------------
# STEP 9: Plot results with the forecast number labeled on chart
# --------------------------------------------------------------
plt.figure(figsize=(10, 5))
plt.plot(monthly['MonthNum'], y, marker='o', label='Actual Monthly Sales')
plt.plot(next_month_num[0], [forecast], 'ro', markersize=10, label=f'Forecast ({next_month_label})')

# Label every actual point with its value
for x_val, y_val in zip(monthly['MonthNum'], y):
    plt.annotate(f'{y_val:,.0f}', (x_val, y_val), textcoords="offset points",
                 xytext=(0, 8), ha='center', fontsize=8, color='dimgray')

# Label the forecast point clearly, above the red dot
plt.annotate(f'{forecast:,.0f}', (next_month_num[0][0], forecast), textcoords="offset points",
             xytext=(0, 12), ha='center', fontsize=10, fontweight='bold', color='red')

plt.xticks(list(monthly['MonthNum']) + next_month_num[0],
           list(monthly['Month'].dt.strftime('%Y-%m')) + [next_month_label], rotation=45)
plt.xlabel('Month')
plt.ylabel('Sales')
plt.title(f'Monthly Sales Trend & Next Month Forecast (source data: {granularity})')
plt.legend()
plt.grid(True, alpha=0.3)
plt.tight_layout()

output_path = os.path.join(os.getcwd(), 'sales_forecast_for_next_month.png')
plt.savefig(output_path, dpi=150)
print(f"\nChart saved as: {output_path}")
plt.show()
