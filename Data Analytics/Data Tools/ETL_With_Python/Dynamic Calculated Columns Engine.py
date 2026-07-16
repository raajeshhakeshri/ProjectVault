import pandas as pd
import numpy as np
import os
import re
from pathlib import Path
from datetime import datetime

# ----------------------------------------------------------------------
# Wrap invalid Python identifiers in backticks
# ----------------------------------------------------------------------
def quote_bad_identifiers(formula, columns):
    ident_re = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')
    cols_sorted = sorted(columns, key=len, reverse=True)
    for col in cols_sorted:
        if ident_re.match(col):
            continue
        escaped = re.escape(col)
        pattern = rf'(?<![a-zA-Z0-9_]){escaped}(?![a-zA-Z0-9_])'
        formula = re.sub(pattern, f'`{col}`', formula)
    return formula

# ----------------------------------------------------------------------
# Parse "Sheet_Column(formula)" or "Column(formula)"
# ----------------------------------------------------------------------
def parse_definition(def_str, is_excel):
    s = def_str.strip()
    paren_start = s.find('(')
    if paren_start == -1 or not s.endswith(')'):
        raise ValueError(f"Invalid format: '{def_str}'. Expected Name(formula)")
    name_part = s[:paren_start].strip()
    formula = s[paren_start+1:-1].strip()
    if is_excel:
        parts = name_part.split('_', 1)
        if len(parts) != 2:
            raise ValueError("Excel definition must be 'Sheet_Column(formula)'. Got: " + def_str)
        sheet_name, col_name = parts
        return sheet_name, col_name, formula
    else:
        return None, name_part, formula

# ----------------------------------------------------------------------
# Main ETL is called
# ----------------------------------------------------------------------
def run_etl():
    file_path = input("Enter the full path of the file (CSV, XLS, XLSX): ").strip().strip('"')
    if not os.path.exists(file_path):
        print(f"Error: File '{file_path}' not found.")
        return

    ext = Path(file_path).suffix.lower()
    if ext not in ('.csv', '.xls', '.xlsx'):
        print("Unsupported file type. Only .csv, .xls, .xlsx are allowed.")
        return

    is_excel = ext in ('.xls', '.xlsx')

    # ==================================================================
    #   EXTENDED DESCRIPTION – ALL POSSIBLE INPUT FORMATS
    # ==================================================================
    print("==================================================================")
    print("                         INSTRUCTIONS                             ")
    print("==================================================================")
    print("\n- Use column names directly (no 'df' prefix needed).")
    print("- Column names with spaces or starting with digits are automatically handled.")
    print("\nSupported operators and functions:")
    print("  Arithmetic: +  -  *  /  //  %  **")
    print("    Examples:  Revenue * 1.1,  Amount / 2,  Value ** 3")
    print("  Comparison: >  <  >=  <=  ==  !=")
    print("    Example:   Price > 100")
    print("  Logical:     and  or  not")
    print("    Example:   (Sales > 100) and (Region == 'West')")
    print("  String:      + (concatenation)")
    print("    Example:   First + ' ' + Last")
    print("  Math functions (via np):")
    print("    Square root: np.sqrt(Value)")
    print("    Power:       np.power(Value, 3)  or  Value ** 3")
    print("    Natural log: np.log(Value)")
    print("    Log base 10: np.log10(Value)")
    print("    Exponential: np.exp(Value)")
    print("    Absolute:    np.abs(Value)")
    print("    Round:       np.round(Value, 2)")
    print("  Conditional:  np.where(condition, true_val, false_val)")
    print("    Example:   np.where(Sales > 1000, 'High', 'Low')")
    print("  Multi-condition: np.select([cond1, cond2], [val1, val2], default)")
    print("  Date functions: pd.to_datetime(DateStr)")
    print("    Example:   (pd.to_datetime(ShipDate) - pd.to_datetime(OrderDate)).dt.days")
    print("==================================================================")
    print("==================================================================")
    print("\nEnter the calculated column definitions.")
    if is_excel:
        print("Format: SheetName_NewColumn( formula )")
        print("Example: Sales_Profit( Revenue - Cost )")
    else:
        print("Format: NewColumn( formula )")
        print("Example: Profit( Revenue - Cost )")
    print("Type 'done' when finished.\n")

    definitions = []
    while True:
        entry = input("> ").strip()
        if entry.lower() == 'done':
            break
        if not entry:
            continue
        try:
            sheet, col, formula = parse_definition(entry, is_excel)
            definitions.append((sheet, col, formula))
        except ValueError as e:
            print(f"Invalid definition: {e}")
            continue

    if not definitions:
        print("No definitions provided. Exiting.")
        return

    out_dir = Path("Transformed")
    out_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # ==================================================================
    # PROCESS CSV Separetly if the file is CSV
    # ==================================================================
    if not is_excel:
        df = pd.read_csv(file_path)
        for _, col, formula in definitions:
            if col in df.columns:
                print(f"⚠️  Warning: Column '{col}' already exists in the CSV. It will be OVERWRITTEN.")
            try:
                safe_formula = quote_bad_identifiers(formula, df.columns)
                df[col] = df.eval(safe_formula, engine='python',
                                  local_dict={'np': np, 'pd': pd})
            except Exception as e:
                print(f"Error on column '{col}': {e}")
                print(f"Formula was: {formula}")
                return

        out_name = out_dir / f"transformed_{Path(file_path).stem}_{timestamp}.csv"
        df.to_csv(out_name, index=False)
        print(f"\n✅ Transformed CSV saved to: {out_name.resolve()}")
        print("Columns in output:", list(df.columns))
        return

    # ==================================================================
    # PROCESS EXCEL Separetly if the file is Excel File
    # ==================================================================
    engine = 'openpyxl' if ext == '.xlsx' else 'xlrd'
    try:
        xl = pd.ExcelFile(file_path, engine=engine)
    except Exception as e:
        print(f"Error reading Excel file: {e}")
        return

    sheet_dict = {name: xl.parse(name) for name in xl.sheet_names}

    for sheet_name, col, formula in definitions:
        if sheet_name not in sheet_dict:
            print(f"⚠️  Sheet '{sheet_name}' not found. Skipping column '{col}'.")
            continue
        df = sheet_dict[sheet_name]
        if col in df.columns:
            print(f"⚠️  Warning: Column '{col}' already exists in sheet '{sheet_name}'. It will be OVERWRITTEN.")
        try:
            safe_formula = quote_bad_identifiers(formula, df.columns)
            df[col] = df.eval(safe_formula, engine='python',
                              local_dict={'np': np, 'pd': pd})
            sheet_dict[sheet_name] = df
        except Exception as e:
            print(f"Error on sheet '{sheet_name}', column '{col}': {e}")
            print(f"Formula: {formula}")
            return

    out_name = out_dir / f"transformed_{Path(file_path).stem}_{timestamp}.xlsx"
    with pd.ExcelWriter(out_name, engine='openpyxl') as writer:
        for sheet, df in sheet_dict.items():
            df.to_excel(writer, sheet_name=sheet, index=False)

    print(f"\n✅ Transformed Excel file saved to: {out_name.resolve()}")
    print("\nFinal columns per sheet:")
    for sheet, df in sheet_dict.items():
        print(f"  Sheet '{sheet}': {list(df.columns)}")

# ==================================================================
# Calling Main Function
# ==================================================================
if __name__ == "__main__":
    run_etl()