# =========================================================================================================
# Importing necessary inbuilt Libraries for ETL:-
#--------------------------------------------------------------------------------------------------------
#import os — Interacts with the operating system (e.g., managing files, folders, and paths).
#import json — Parses, reads, and writes JSON-formatted data.
#mport re - Performs advanced text searching and pattern matching using regular expressions.
#import xml.etree.ElementTree as ET - Navigates and creates XML-structured data files.
#import pandas as pd - Analyses,filters and manipulates tabular data structures (like tables/DataFrames).
#from datetime import datetime — Works with,formats and calculates dates and times.
# =========================================================================================================

import os
import json
import re
import xml.etree.ElementTree as ET
import pandas as pd
from datetime import datetime

# ===========================
# OUTPUT DIRECTORIES
# ===========================
# Used by the ETL transformation step (final output for all file types)
OUTPUT_DIRECTORY = r"C:\Users\RAJESH\OneDrive\Desktop\ETL_OUTPUT"
os.makedirs(OUTPUT_DIRECTORY, exist_ok=True)

# Shared backup folder (holds backups of transformed XLS/XLSX/CSV files
# produced by the ETL step)
BACKUP_DIRECTORY = os.path.join(OUTPUT_DIRECTORY, "backup")
os.makedirs(BACKUP_DIRECTORY, exist_ok=True)

# Dedicated folder for the JSON/XML -> CSV conversion output
CONVERTED_DIRECTORY = os.path.join(OUTPUT_DIRECTORY, "Converted")
os.makedirs(CONVERTED_DIRECTORY, exist_ok=True)


# ==============================================================================
# ==============================================================================
# SECTION 1 : JSON / XML  ->  CSV CONVERSION
# ==============================================================================
# ==============================================================================

# ------------------------------------------------------------------------------
# GENERATE OUTPUT CSV NAME
# ------------------------------------------------------------------------------
def get_output_filename(input_file):
    """
    Generate output filename in the format:
    filename_YYYYMMDD_HHMMSS.csv
    and save it directly to the converted folder.
    """

    # Create output directory if it doesn't exist
    os.makedirs(CONVERTED_DIRECTORY, exist_ok=True)

    filename = os.path.splitext(os.path.basename(input_file))[0]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    return os.path.join(
        CONVERTED_DIRECTORY,
        f"{filename}_{timestamp}.csv"
    )


# ------------------------------------------------------------------------------
# FLATTEN NESTED DICTIONARY
# ------------------------------------------------------------------------------
def flatten_dict(data, parent_key="", sep="_"):
    """
    Recursively flattens nested dictionaries.
    Lists of primitive values are converted to comma-separated strings.
    Lists of dictionaries are handled separately during row detection.
    """
    items = {}

    if isinstance(data, dict):

        for key, value in data.items():

            new_key = f"{parent_key}{sep}{key}" if parent_key else key

            if isinstance(value, dict):

                items.update(flatten_dict(value, new_key, sep))

            elif isinstance(value, list):

                # Primitive list
                if all(not isinstance(x, (dict, list)) for x in value):
                    items[new_key] = ",".join(map(str, value))

                # Ignore list of dictionaries (handled separately)
                else:
                    continue

            else:

                items[new_key] = value

    return items


# ------------------------------------------------------------------------------
# FIND FIRST REPEATING LIST OF DICTIONARIES
# ------------------------------------------------------------------------------
def find_record_list(data):
    """
    Recursively searches for the first repeating list of dictionaries.
    """

    if isinstance(data, list):

        if len(data) > 0 and isinstance(data[0], dict):
            return data

    elif isinstance(data, dict):

        for value in data.values():

            result = find_record_list(value)

            if result is not None:
                return result

    return None


# ------------------------------------------------------------------------------
# JSON TO CSV
# ------------------------------------------------------------------------------
def json_to_csv(json_file):

    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    rows = []

    record_list = find_record_list(data)

    if record_list:

        for record in record_list:
            rows.append(flatten_dict(record))

    else:

        rows.append(flatten_dict(data))

    df = pd.DataFrame(rows)

    output = get_output_filename(json_file)

    df.to_csv(
        output,
        index=False,
        encoding="utf-8-sig"
    )

    print("\nPreview\n")
    print(df.head())

    print(f"\nCSV Saved : {output}")

    # Return the generated CSV path so it can be fed into the ETL step
    return output


# ------------------------------------------------------------------------------
# XML ELEMENT TO DICTIONARY
# ------------------------------------------------------------------------------
def xml_to_dict(element):

    result = {}

    # Attributes
    for key, value in element.attrib.items():
        result[f"@{key}"] = value

    children = list(element)

    if not children:

        text = element.text.strip() if element.text else ""

        if result:
            result["value"] = text
            return result

        return text

    for child in children:

        child_value = xml_to_dict(child)

        if child.tag in result:

            if not isinstance(result[child.tag], list):
                result[child.tag] = [result[child.tag]]

            result[child.tag].append(child_value)

        else:

            result[child.tag] = child_value

    return result


# ------------------------------------------------------------------------------
# XML TO CSV
# ------------------------------------------------------------------------------
def xml_to_csv(xml_file):

    tree = ET.parse(xml_file)

    root = tree.getroot()

    data = xml_to_dict(root)

    rows = []

    record_list = find_record_list(data)

    if record_list:

        for record in record_list:
            rows.append(flatten_dict(record))

    else:

        rows.append(flatten_dict(data))

    df = pd.DataFrame(rows)

    output = get_output_filename(xml_file)

    df.to_csv(
        output,
        index=False,
        encoding="utf-8-sig"
    )

    print("\nPreview\n")
    print(df.head())

    print(f"\nCSV Saved : {output}")

    # Return the generated CSV path so it can be fed into the ETL step
    return output
    
# ==============================================================================
# SECTION 1 Ends
# ==============================================================================

# ==============================================================================
# ==============================================================================
# SECTION 2 Starts : 
#   CSV / XLS / XLSX  -> ETL Transformation directly                 -> Transformed CSV/XLSX
#   JSON              -> Step 1: JSON -> CSV, Step 2: ETL on that CSV -> Transformed CSV
#   XML               -> Step 1: XML -> CSV,  Step 2: ETL on that CSV -> Transformed CSV
# ==============================================================================
# ==============================================================================

def process_file(file_path: str):
    """
    Dispatch a single file through the correct pipeline based on its extension,
    per the required Input Type -> Step 1 -> Step 2 -> Final Output framework.
    """
    ext = os.path.splitext(file_path)[1].lower()

    if ext in [".csv", ".xls", ".xlsx"]:
        # Step 1: ETL Transformation directly (no conversion needed)
        convert_file(file_path)

    elif ext == ".json":
        # Step 1: Convert JSON -> CSV
        intermediate_csv = json_to_csv(file_path)
        # Step 2: Run existing ETL on the generated CSV
        convert_file(intermediate_csv)

    elif ext == ".xml":
        # Step 1: Convert XML -> CSV
        intermediate_csv = xml_to_csv(file_path)
        # Step 2: Run existing ETL on the generated CSV
        convert_file(intermediate_csv)

    else:
        print(f"Unsupported file format: {file_path} (only .csv, .xls, .xlsx, .json, .xml are supported)")

# ==============================================================================
# ==============================================================================
# SECTION 3 : ETL TRANSFORMATION (CSV / XLS / XLSX)
# ==============================================================================
# ==============================================================================

# ---------------- Configuration ----------------
# Inline configuration for uppercase normalization and validation rules
CONFIG = {
    "uppercase_columns": [
        "Country", "Country Code", "State", "State Code", "Region", "Zone", "Territory",
        "Currency Code", "Language Code", "Employee ID", "Customer ID", "Vendor ID",
        "Supplier ID", "Product Code", "SKU", "Item Code", "Batch Number", "Serial Number",
        "Invoice Number", "Purchase Order Number", "Sales Order Number", "Shipment Number",
        "Tracking Number", "Ticket Number", "PAN", "GSTIN", "TAN", "CIN", "IFSC",
        "SWIFT Code", "MICR Code", "Passport Number", "Vehicle Registration Number",
        "HSN Code", "SAC Code", "Department Code", "Company Code", "Business Unit",
        "Division Code", "Cost Center", "Profit Center", "Project Code", "Branch Code",
        "Warehouse Code", "Plant Code", "Store Code", "Location Code", "Status",
        "Approval Status", "Priority", "Risk Level", "Gender Code", "Marital Status",
        "Blood Group", "Payment Mode", "Environment", "Database Code", "Table Prefix",
        "File Extension"
    ],
    "validation_rules": {
        "PAN": r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$",
        "GSTIN": r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[0-9A-Z]{1}[Z]{1}[0-9A-Z]{1}$",
        "IFSC": r"^[A-Z]{4}0[A-Z0-9]{6}$",
    },
    "null_tokens": ["", "NA", "N/A", "NULL", "NONE", "-"]
}

# ---------------- Logging ----------------
def log(message: str, log_file: str):
    """Append a timestamped message to the log file."""
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] | {message}\n")

# ---------------- Utility Helpers ----------------
def proper_case(s):
    return s.title() if isinstance(s, str) else s

def remove_invisible_chars(s: str) -> str:
    """Remove tabs, CR, LF, zero-width, non-breaking spaces and other invisible unicode chars."""
    if not isinstance(s, str):
        return s
    return re.sub(r'[\t\r\n\u200B\u00A0\u200C\u200D\uFEFF]', '', s)

def collapse_spaces(s: str) -> str:
    """Trim and collapse multiple spaces into single space."""
    if not isinstance(s, str):
        return s
    return re.sub(r'\s+', ' ', s.strip())

def is_null_token(s: str, null_tokens) -> bool:
    if s is None:
        return True
    if not isinstance(s, str):
        return False
    return s.strip().upper() in {t.upper() for t in null_tokens}

def unicode_upper(s: str) -> str:
    """Unicode-safe uppercase conversion, locale-independent."""
    if not isinstance(s, str):
        return s
    return s.upper()

def preserve_structure_upper(s: str) -> str:
    """
    Apply the transformation rules:
    - Treat configured null tokens as None
    - Remove invisible characters
    - Trim and collapse spaces
    - Convert alphabetic characters to uppercase (preserve digits and allowed symbols)
    """
    if pd.isna(s):
        return None

    s = str(s)

    # Step 2: treat null tokens as NULL
    if is_null_token(s, CONFIG["null_tokens"]):
        return None

    # Step 3: remove invisible characters
    s = remove_invisible_chars(s)

    # Step 4: trim and collapse spaces
    s = collapse_spaces(s)

    # Step 5: convert to uppercase (preserve digits and valid symbols)
    s = unicode_upper(s)

    return s

def validate_value(col: str, val: str, rules: dict) -> (bool, str):
    """Validate value using regex rule if present. Returns (is_valid, reason)."""
    if val is None:
        return True, "SKIPPED_NULL"
    rule = rules.get(col)
    if not rule:
        return True, "NO_RULE"
    try:
        if re.fullmatch(rule, val):
            return True, "VALID"
        else:
            return False, "INVALID_PATTERN"
    except re.error:
        return False, "INVALID_REGEX"

def check_series_condition(series: pd.Series) -> bool:
    """Check if at least 90% of integer values follow a strict series (difference of 1)."""
    numeric = pd.to_numeric(series, errors='coerce').dropna()
    if numeric.empty:
        return False
    try:
        numeric_int = numeric.astype(int)
    except Exception:
        return False
    if len(numeric_int) < 2:
        return False
    diffs = numeric_int.diff().dropna()
    valid = (diffs == 1).sum()
    return (valid / len(diffs)) >= 0.9

# ==============================================================================
# Core Transformation Starts from Here
# ==============================================================================
def transform_dataframe(df: pd.DataFrame, log_file: str, sheet_name: str = "Sheet1") -> pd.DataFrame:
  
    log(f"--- Processing Sheet: {sheet_name} ---", log_file)

    # Row/Column counting
    rows, cols = df.shape
    log(f"Sheet '{sheet_name}': Row Count={rows}, Column Count={cols}", log_file)

    # Blank counts and "NA"/"N/A" counts per column
    for col in df.columns:
        na_count = df[col].isna().sum()
        empty_str_count = 0
        try:
            empty_str_count = df[col].astype(str).str.strip().eq("").sum()
        except Exception:
            empty_str_count = 0
        token_count = df[col].astype(str).str.upper().isin(["NA", "N/A"]).sum()
        total_blanks = int(na_count + empty_str_count)
        log(f"Sheet '{sheet_name}' Column '{col}': Blanks={total_blanks}, NA/NAs={int(token_count)}", log_file)

    # Column names cleaning (remove special chars like - ? ! $ % and Proper case)
    original_columns = list(df.columns)
    cleaned_columns = [re.sub(r'[?!$%]', '', col).title() for col in original_columns]
    df.columns = cleaned_columns
    log(f"Sheet '{sheet_name}': Column names cleaned. Original -> Cleaned mapping logged.", log_file)
    for o, c in zip(original_columns, cleaned_columns):
        if o != c:
            log(f"Sheet '{sheet_name}': Column rename: '{o}' -> '{c}'", log_file)

    # Apply string cleaning and uppercase Normalization for eligible columns
    string_cols = df.select_dtypes(include=['object']).columns.tolist()
    rules = CONFIG.get("validation_rules", {})

    for col in string_cols:
        original_series = df[col].copy()

        # Treat configured null tokens as actual NaN
        df[col] = df[col].apply(lambda x: None if is_null_token(x, CONFIG["null_tokens"]) else x)

        # Remove invisible chars and collapse spaces
        df[col] = df[col].astype(object).apply(lambda x: remove_invisible_chars(str(x)) if x is not None else None)
        df[col] = df[col].astype(object).apply(lambda x: collapse_spaces(x) if x is not None else None)

        # Uppercase only for configured columns
        if col in CONFIG.get("uppercase_columns", []):
            df[col] = df[col].apply(lambda x: preserve_structure_upper(x) if x is not None else None)

            # Audit logging and validation per changed value
            for idx, (o, t) in enumerate(zip(original_series.tolist(), df[col].tolist())):
                o_display = None if pd.isna(o) or is_null_token(o, CONFIG["null_tokens"]) else str(o)
                t_display = None if t is None else str(t)
                if o_display != t_display:
                    is_valid, reason = validate_value(col, t_display, rules)
                    status = "VALID" if is_valid else "INVALID"
                    log(f"Sheet='{sheet_name}', Row={idx}, Column='{col}', Original='{o_display}', Transformed='{t_display}', Validation={status}, Reason={reason}", log_file)
        else:
            # For non-configured string columns log visible changes
            for idx, (o, t) in enumerate(zip(original_series.tolist(), df[col].tolist())):
                o_display = None if pd.isna(o) or is_null_token(o, CONFIG["null_tokens"]) else str(o)
                t_display = None if t is None else str(t)
                if o_display != t_display:
                    log(f"Sheet='{sheet_name}', Row={idx}, Column='{col}', Original='{o_display}', Transformed='{t_display}', Transformation=TRIM_CLEAN'", log_file)

    log(f"Sheet '{sheet_name}': String normalization complete.", log_file)

    # Conditional forward/backward fill for numeric columns as per condition
    numeric_cols = df.select_dtypes(include=['int64', 'float64']).columns.tolist()
    object_numeric_candidates = [c for c in df.select_dtypes(include=['object']).columns if pd.to_numeric(df[c], errors='coerce').notna().sum() > 0]

    for col in numeric_cols:
        try:
            if check_series_condition(df[col]):
                df[col] = df[col].fillna(method='ffill').fillna(method='bfill')
                log(f"Sheet '{sheet_name}': Forward/Backward fill applied on numeric column '{col}' (series condition met).", log_file)
            else:
                log(f"Sheet '{sheet_name}': Forward/Backward fill skipped on numeric column '{col}' (series condition not met).", log_file)
        except Exception as e:
            log(f"Sheet '{sheet_name}': Error checking series condition for column '{col}': {e}", log_file)

    for col in object_numeric_candidates:
        try:
            if check_series_condition(df[col]):
                log(f"Sheet '{sheet_name}': Column '{col}' is object but numeric-like and meets series condition; fill skipped to preserve original dtype.", log_file)
            else:
                log(f"Sheet '{sheet_name}': Column '{col}' is object and does not meet series condition.", log_file)
        except Exception as e:
            log(f"Sheet '{sheet_name}': Error checking series condition for object column '{col}': {e}", log_file)

    # Detect duplicate rows (complete duplicates only as per condition ) and delete them
    try:
        dup_mask = df.duplicated(keep=False)
        if dup_mask.any():
            dup_indices = df[dup_mask].index.tolist()
            log(f"Sheet '{sheet_name}': Duplicate rows detected at indices: {dup_indices}", log_file)
            before_count = len(df)
            df = df.drop_duplicates(keep='first').reset_index(drop=True)
            after_count = len(df)
            deleted = before_count - after_count
            log(f"Sheet '{sheet_name}': Complete duplicate rows deleted: {deleted}", log_file)
        else:
            log(f"Sheet '{sheet_name}': No complete duplicate rows detected.", log_file)
    except Exception as e:
        log(f"Sheet '{sheet_name}': Error detecting/deleting duplicate rows: {e}", log_file)

    # Detect duplicate columns
    try:
        dup_cols = [col for col in df.columns[df.columns.duplicated(keep=False)].tolist()]
        if dup_cols:
            dup_info = []
            for c in set(dup_cols):
                positions = [i for i, name in enumerate(df.columns.tolist()) if name == c]
                dup_info.append(f"Column='{c}' Positions={positions}")
            log(f"Sheet '{sheet_name}': Duplicate columns detected: {', '.join(dup_info)}", log_file)
        else:
            log(f"Sheet '{sheet_name}': No duplicate columns detected.", log_file)
    except Exception as e:
        log(f"Sheet '{sheet_name}': Error detecting duplicate columns: {e}", log_file)

    # Identify invalid numeric values (negative ages, salaries, quantities, prices)and log it in logs only(no Transformation)
    for col in df.columns:
        try:
            numeric_copy = pd.to_numeric(df[col], errors='coerce')
            if "age" in col.lower() and (numeric_copy < 0).any():
                log(f"Sheet '{sheet_name}': Invalid ages found in '{col}': {numeric_copy[numeric_copy < 0].dropna().tolist()}", log_file)
            if "salary" in col.lower() and (numeric_copy < 0).any():
                log(f"Sheet '{sheet_name}': Invalid salaries found in '{col}': {numeric_copy[numeric_copy < 0].dropna().tolist()}", log_file)
            if "quantity" in col.lower() and (numeric_copy < 0).any():
                log(f"Sheet '{sheet_name}': Invalid quantities found in '{col}': {numeric_copy[numeric_copy < 0].dropna().tolist()}", log_file)
            if "price" in col.lower() and (numeric_copy < 0).any():
                log(f"Sheet '{sheet_name}': Invalid prices found in '{col}': {numeric_copy[numeric_copy < 0].dropna().tolist()}", log_file)
        except Exception as e:
            log(f"Sheet '{sheet_name}': Error validating numeric values for column '{col}': {e}", log_file)

    # Delivery date vs Order Date checks (if both present)
    if any("delivery" in c.lower() and "date" in c.lower() for c in df.columns) and "Order Date" in df.columns:
        for col in df.columns:
            if "delivery" in col.lower() and "date" in col.lower():
                for idx, row in df.iterrows():
                    try:
                        delivery_val = row[col]
                        order_val = row["Order Date"]
                        if pd.notna(delivery_val) and pd.notna(order_val):
                            if pd.to_datetime(delivery_val, errors='coerce') < pd.to_datetime(order_val, errors='coerce'):
                                log(f"Sheet '{sheet_name}': Delivery before order at row {idx}: {delivery_val} < {order_val}", log_file)
                    except Exception:
                        pass

    # Outlier detection beside numeric columns (inserting OutlierFlag column next to original Column)
    candidate_cols = df.select_dtypes(include=['int64', 'float64', 'object']).columns.tolist()
    for col in candidate_cols:
        try:
            numeric_copy = pd.to_numeric(df[col], errors='coerce')
            if numeric_copy.dropna().empty:
                continue
            Q1 = numeric_copy.quantile(0.25)
            Q3 = numeric_copy.quantile(0.75)
            IQR = Q3 - Q1
            lower_bound = Q1 - 1.5 * IQR
            upper_bound = Q3 + 1.5 * IQR
            outlier_col = f"{col}_OutlierFlag"
            flags = numeric_copy.apply(lambda x: "Outlier" if pd.notnull(x) and (x < lower_bound or x > upper_bound) else "Normal Data")
            insert_pos = df.columns.get_loc(col) + 1
            if outlier_col in df.columns:
                suffix = 1
                while f"{outlier_col}_{suffix}" in df.columns:
                    suffix += 1
                outlier_col = f"{outlier_col}_{suffix}"
            df.insert(insert_pos, outlier_col, flags)
            log(f"Sheet '{sheet_name}': Outlier detection applied on '{col}'. Bounds: lower={lower_bound}, upper={upper_bound}", log_file)
        except Exception as e:
            log(f"Sheet '{sheet_name}': Error during outlier detection for column '{col}': {e}", log_file)

    log(f"--- Completed Sheet: {sheet_name} ---", log_file)
    return df
   
# ---------------- File Conversion and Orchestration ----------------
def convert_file(file_path: str):
    """
    Load file (CSV, XLSX, JSON, TXT), apply transformations to each sheet,
    save outputs (XLSX for Excel input, CSV for others)
    """
    # Normalize path to avoid permission issues
    file_path = os.path.normpath(file_path.replace("\\", "/"))

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Input file not found: {file_path}")
    ext = os.path.splitext(file_path)[1].lower()
    timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M%S")
    base_name = os.path.splitext(os.path.basename(file_path))[0]

    # Sub-folders under OUTPUT_DIRECTORY: backup,transformed,log
    BACKUP_DIRECTORY = os.path.join(OUTPUT_DIRECTORY, "Backup")
    TRANSFORMED_DIRECTORY = os.path.join(OUTPUT_DIRECTORY, "Transformed")
    LOG_DIRECTORY = os.path.join(OUTPUT_DIRECTORY, "Log")
    os.makedirs(BACKUP_DIRECTORY, exist_ok=True)
    os.makedirs(TRANSFORMED_DIRECTORY, exist_ok=True)
    os.makedirs(LOG_DIRECTORY, exist_ok=True)

    log_file = os.path.join(LOG_DIRECTORY, f"log_{base_name}_{timestamp}.txt")

    # Summary containers
    per_sheet_summary = {}
    aggregated = {
        "total_sheets": 0,
        "total_rows": 0,
        "total_columns": 0,
        "total_blank_cells": 0,
        "total_na_tokens": 0,
        "total_duplicate_rows_deleted": 0,
        "columns_outlier_counts": {},  
        "columns_blank_counts": {},    
        "columns_na_counts": {},       
        "forward_fill_applied_columns": [],
        "forward_fill_skipped_columns": []
    }

    # Load sheets
    if ext in ['.csv']:
        df = pd.read_csv(file_path, dtype=object)
        sheets = {"Sheet1": df}
        output_format = "csv"
    elif ext in ['.xlsx', '.xls']:
        sheets = pd.read_excel(file_path, sheet_name=None, dtype=object)
        output_format = "xlsx"
    else:
        raise ValueError("Unsupported file format")

    log(f"File '{file_path}' loaded successfully. Detected sheets: {list(sheets.keys())}", log_file)

    transformed_sheets = {}
    for sheet_name, df in sheets.items():
        df = df.copy()
        # Apply transformations (this function logs detailed per-sheet actions)
        transformed_df = transform_dataframe(df, log_file, sheet_name)
        transformed_sheets[sheet_name] = transformed_df

        # Build per-sheet summary in logs file
        sheet_rows, sheet_cols = transformed_df.shape
        per_sheet = {
            "rows": sheet_rows,
            "columns": sheet_cols,
            "blank_cells": 0,
            "na_tokens": 0,
            "duplicate_rows_deleted": None,  # logged earlier; we can infer by comparing original and transformed if original known
            "outliers_per_column": {},
            "blanks_per_column": {},
            "na_per_column": {},
            "forward_fill_applied_columns": [],
            "forward_fill_skipped_columns": []
        }

        # Count blanks and "NA" when identified per column and aggregate it as total 
        for col in transformed_df.columns:
            try:
                blanks = int(transformed_df[col].isna().sum() + transformed_df[col].astype(str).str.strip().eq("").sum())
            except Exception:
                blanks = int(transformed_df[col].isna().sum())
            try:
                na_tokens = int(transformed_df[col].astype(str).str.upper().isin(["NA", "N/A"]).sum())
            except Exception:
                na_tokens = 0

            per_sheet["blanks_per_column"][col] = blanks
            per_sheet["na_per_column"][col] = na_tokens
            per_sheet["blank_cells"] += blanks
            per_sheet["na_tokens"] += na_tokens

            # Aggregate per-column counts across sheets
            aggregated["columns_blank_counts"][col] = aggregated["columns_blank_counts"].get(col, 0) + blanks
            aggregated["columns_na_counts"][col] = aggregated["columns_na_counts"].get(col, 0) + na_tokens

        # Outlier counts: detect any *_OutlierFlag columns and count Outlier values
        for col in transformed_df.columns:
            if col.endswith("_OutlierFlag"):
                try:
                    outlier_count = int(transformed_df[col].astype(str).str.upper().eq("OUTLIER").sum())
                except Exception:
                    outlier_count = 0
                # Map back to original column name (strip suffix)
                orig_col = col[:-12]  # remove "_OutlierFlag"
                per_sheet["outliers_per_column"][orig_col] = outlier_count
                aggregated["columns_outlier_counts"][orig_col] = aggregated["columns_outlier_counts"].get(orig_col, 0) + outlier_count

        # Attempt to detect which numeric columns had forward/backward fill applied by re-checking series condition
        for col in transformed_df.select_dtypes(include=['int64', 'float64']).columns.tolist():
            try:
                if check_series_condition(transformed_df[col]):
                    per_sheet["forward_fill_applied_columns"].append(col)
                    aggregated["forward_fill_applied_columns"].append(f"{sheet_name}:{col}")
                else:
                    per_sheet["forward_fill_skipped_columns"].append(col)
                    aggregated["forward_fill_skipped_columns"].append(f"{sheet_name}:{col}")
            except Exception:
                per_sheet["forward_fill_skipped_columns"].append(col)
                aggregated["forward_fill_skipped_columns"].append(f"{sheet_name}:{col}")

        # Duplicate rows deletion: infer by comparing original loaded sheet row count vs transformed row count
        try:
            original_count = sheets[sheet_name].shape[0]
            deleted = original_count - transformed_df.shape[0]
            per_sheet["duplicate_rows_deleted"] = int(deleted if deleted > 0 else 0)
            aggregated["total_duplicate_rows_deleted"] += per_sheet["duplicate_rows_deleted"]
        except Exception:
            per_sheet["duplicate_rows_deleted"] = None

        # Update aggregated totals
        aggregated["total_sheets"] += 1
        aggregated["total_rows"] += per_sheet["rows"]
        aggregated["total_columns"] += per_sheet["columns"]
        aggregated["total_blank_cells"] += per_sheet["blank_cells"]
        aggregated["total_na_tokens"] += per_sheet["na_tokens"]

        per_sheet_summary[sheet_name] = per_sheet
        
# ==============================================
# Core Transformtion Ends here;
# ==============================================


# ==============================================
# Core Logging sumaary starts here :--
# ==============================================
    # Writing a comprehensive summary at the end of the log
    log("=== ETL EXECUTION SUMMARY (Lead Analyst View) ===", log_file)
    log(f"Processed file: {file_path}", log_file)
    log(f"Execution timestamp: {datetime.now().strftime('%Y_%m_%d_%H_%M%S')}", log_file)
    log(f"Number of sheets processed: {aggregated['total_sheets']}", log_file)
    log(f"Total rows across all sheets (sum): {aggregated['total_rows']}", log_file)
    log(f"Total columns across all sheets (sum): {aggregated['total_columns']}", log_file)
    log(f"Total blank cells across all sheets: {aggregated['total_blank_cells']}", log_file)
    log(f"Total NA/NAs tokens across all sheets: {aggregated['total_na_tokens']}", log_file)
    log(f"Total complete duplicate rows deleted across all sheets: {aggregated['total_duplicate_rows_deleted']}", log_file)

    # Forward/backward fill summary
    log("Forward/Backward Fill Summary:", log_file)
    log(f"  Columns where fill was applied (sheet:column): {', '.join(aggregated['forward_fill_applied_columns']) if aggregated['forward_fill_applied_columns'] else 'None'}", log_file)
    log(f"  Columns where fill was skipped (sheet:column): {', '.join(aggregated['forward_fill_skipped_columns']) if aggregated['forward_fill_skipped_columns'] else 'None'}", log_file)

    # Per-sheet detailed summary
    for sheet_name, summary in per_sheet_summary.items():
        log(f"--- Sheet: {sheet_name} Summary ---", log_file)
        log(f"Rows: {summary['rows']}, Columns: {summary['columns']}", log_file)
        log(f"Blank cells (sheet): {summary['blank_cells']}, NA/NAs (sheet): {summary['na_tokens']}", log_file)
        log(f"Duplicate rows deleted (sheet): {summary['duplicate_rows_deleted']}", log_file)
        # Outliers per column
        if summary["outliers_per_column"]:
            for col, cnt in summary["outliers_per_column"].items():
                log(f"Outliers in column '{col}': {cnt}", log_file)
        else:
            log("No outlier flags detected in this sheet.", log_file)
        # Top 5 columns by "blanks"
        try:
            top_blanks = sorted(summary["blanks_per_column"].items(), key=lambda x: x[1], reverse=True)[:5]
            log(f"Top columns by blanks (top 5): {top_blanks}", log_file)
        except Exception:
            pass
        # Top 5 columns by "NA" tokens
        try:
            top_nas = sorted(summary["na_per_column"].items(), key=lambda x: x[1], reverse=True)[:5]
            log(f"Top columns by NA/NAs (top 5): {top_nas}", log_file)
        except Exception:
            pass
        # Forward fill columns
        log(f"Forward fill applied columns (sheet): {summary['forward_fill_applied_columns'] if summary['forward_fill_applied_columns'] else 'None'}", log_file)
        log(f"Forward fill skipped columns (sheet): {summary['forward_fill_skipped_columns'] if summary['forward_fill_skipped_columns'] else 'None'}", log_file)

    # Aggregated outlier summary across sheets
    if aggregated["columns_outlier_counts"]:
        log("=== Aggregated Outlier Counts Across Sheets ===", log_file)
        for col, cnt in aggregated["columns_outlier_counts"].items():
            log(f"Column '{col}': Total Outliers={cnt}", log_file)
    else:
        log("No aggregated outlier counts detected across sheets.", log_file)

    # Aggregated "blanks"/"NA" per column
    try:
        if aggregated["columns_blank_counts"]:
            top_blank_cols = sorted(aggregated["columns_blank_counts"].items(), key=lambda x: x[1], reverse=True)[:10]
            log(f"Top columns by aggregated blanks (top 10): {top_blank_cols}", log_file)
        if aggregated["columns_na_counts"]:
            top_na_cols = sorted(aggregated["columns_na_counts"].items(), key=lambda x: x[1], reverse=True)[:10]
            log(f"Top columns by aggregated NA/NAs (top 10): {top_na_cols}", log_file)
    except Exception:
        pass

    log("=== End of ETL EXECUTION SUMMARY ===", log_file)

    # Saving outputs (output -> transformed folder, backup -> backup folder)
    if output_format == "csv":
        first_sheet = list(transformed_sheets.keys())[0]
        csv_path = os.path.join(TRANSFORMED_DIRECTORY,f"{base_name}_transformed_{timestamp}.csv")
        backup_path = os.path.join(BACKUP_DIRECTORY,f"{base_name}_backup_{timestamp}.csv")
        transformed_sheets[first_sheet].to_csv(csv_path, index=False)
        sheets[first_sheet].to_csv(backup_path, index=False)
        log(f"CSV file saved at {csv_path}", log_file)
        log(f"Backup CSV file saved at {backup_path}", log_file)
        print(f"CSV file saved at: {csv_path}")
        print(f"Backup CSV file saved at: {backup_path}")
    else:
        xlsx_path = os.path.join(TRANSFORMED_DIRECTORY,f"{base_name}_transformed_{timestamp}.xlsx")
        backup_xlsx_path = os.path.join(BACKUP_DIRECTORY,f"{base_name}_backup_{timestamp}.xlsx")
        with pd.ExcelWriter(xlsx_path, engine="xlsxwriter") as writer:
            for sheet_name, df in transformed_sheets.items():
                df.to_excel(writer, sheet_name=sheet_name[:31], index=False)
        with pd.ExcelWriter(backup_xlsx_path, engine="xlsxwriter") as writer:
            for sheet_name, df in sheets.items():
                df.to_excel(writer, sheet_name=sheet_name[:31], index=False)
        log(f"Transformed XLSX file saved at {xlsx_path}", log_file)
        log(f"Backup XLSX file saved at {backup_xlsx_path}", log_file)
        print(f"Transformed XLSX file saved at: {xlsx_path}")
        print(f"Backup XLSX file saved at: {backup_xlsx_path}")

    log(f"Transformation log saved at: {log_file}", log_file)
    print(f"Transformation log saved at: {log_file}")
    print("ETL Completed")



# ===============================
# Main Function Starts
# ===============================
def main():
    input_path = input(
        "Enter the path of the CSV/XLS/XLSX/JSON/XML file OR a folder containing files: "
    ).strip().strip('"')

    if not os.path.exists(input_path):
        print("\nError : Path does not exist.")
        return

    try:

        supported_extensions = (".csv", ".xls", ".xlsx", ".json", ".xml")

        # ----------------------------------------------------------------------
        # If a folder is provided, process all supported files
        # ----------------------------------------------------------------------
        if os.path.isdir(input_path):

            files = [
                os.path.join(input_path, file)
                for file in os.listdir(input_path)
                if file.lower().endswith(supported_extensions)
            ]

            if not files:
                print("\nNo supported files (.csv, .xls, .xlsx, .json, .xml) found in the folder.")
                return

            print(f"\nFound {len(files)} file(s).\n")

            for file_path in files:

                print("=" * 70)
                print(f"Processing : {os.path.basename(file_path)}")
                print("=" * 70)

                try:
                    process_file(file_path)
                except Exception as ex:
                    print(f"Error processing {os.path.basename(file_path)} : {ex}")

            print("\nAll files processed successfully.")

        # ----------------------------------------------------------------------
        # If a single file is provided
        # ----------------------------------------------------------------------
        else:

            ext = os.path.splitext(input_path)[1].lower()

            if ext not in supported_extensions:
                print("Only CSV,XLS,XLSX,JSON and XML files are supported.")
                return

            try:
                process_file(input_path)
            except Exception as ex:
                print(f"Error: {ex}")

    except Exception as ex:
        print("\nError :", ex)
        
# ===============================
# Main Function ends
# ===============================


# ===============================
# Calling Main Function
# ===============================
if __name__ == "__main__":
    main()
