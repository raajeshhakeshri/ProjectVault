import os
import json
import xml.etree.ElementTree as ET
import pandas as pd
from datetime import datetime

# ==============================================================================
#OUTPUT DIRECTORY
# ==============================================================================
OUTPUT_DIRECTORY = r"C:\Users\RAJESH\OneDrive\Desktop\index\OUTPUT"      


# ==============================================================================
# GENERATE OUTPUT CSV NAME
# ==============================================================================
def get_output_filename(input_file):
    """
    Generate output filename in the format:
    filename_YYYYMMDD_HHMMSS.csv
    and save it to the hardcoded output directory.
    """

    # Create output directory if it doesn't exist
    os.makedirs(OUTPUT_DIRECTORY, exist_ok=True)

    filename = os.path.splitext(os.path.basename(input_file))[0]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    return os.path.join(
        OUTPUT_DIRECTORY,
        f"{filename}_{timestamp}.csv"
    )


# ==============================================================================
# FLATTEN NESTED DICTIONARY
# ==============================================================================
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


# ==============================================================================
# FIND FIRST REPEATING LIST OF DICTIONARIES
# ==============================================================================
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


# ==============================================================================
# JSON TO CSV
# ==============================================================================
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


# ==============================================================================
# XML ELEMENT TO DICTIONARY
# ==============================================================================
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


# ==================
# XML TO CSV
# ==================
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



# ==============================================================================
# MAIN FUNCTION
# ==============================================================================
def main():

    input_path = input(
        "Enter the path of XML/JSON file OR folder containing XML/JSON files: "
    ).strip('"')

    if not os.path.exists(input_path):
        print("\nError : Path does not exist.")
        return

    try:

        # ----------------------------------------------------------------------
        # If a folder is provided, process all XML and JSON files
        # ----------------------------------------------------------------------
        if os.path.isdir(input_path):

            files = [
                os.path.join(input_path, file)
                for file in os.listdir(input_path)
                if os.path.splitext(file)[1].lower() in [".json", ".xml"]
            ]

            if not files:
                print("\nNo XML or JSON files found in the folder.")
                return

            print(f"\nFound {len(files)} file(s).\n")

            for file_path in files:

                print("=" * 70)
                print(f"Processing : {os.path.basename(file_path)}")
                print("=" * 70)

                extension = os.path.splitext(file_path)[1].lower()

                try:

                    if extension == ".json":
                        json_to_csv(file_path)

                    elif extension == ".xml":
                        xml_to_csv(file_path)

                except Exception as ex:

                    print(f"Error processing {os.path.basename(file_path)} : {ex}")

            print("\nAll files processed successfully.")

        # ----------------------------------------------------------------------
        # If a single file is provided (existing functionality)
        # ----------------------------------------------------------------------
        else:

            extension = os.path.splitext(input_path)[1].lower()

            if extension == ".json":

                json_to_csv(input_path)

            elif extension == ".xml":

                xml_to_csv(input_path)

            else:

                print("Only XML and JSON files are supported.")

    except Exception as ex:

        print("\nError :", ex)

# =====================
# Calling Main Function
# =====================
if __name__ == "__main__":
    main()