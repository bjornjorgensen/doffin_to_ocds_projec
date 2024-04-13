# src/read_write.py
import json
from lxml import etree
import sys

# Assume mapper3.py is stored in the same directory
from mapper3 import eform_to_ocds  # Adjust the import path if necessary

def read_xml_file(file_path):
    with open(file_path, 'rb') as file:
        return file.read()

def write_json_file(data, file_path):
    with open(file_path, 'w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=4)

def main(xml_input_path, json_output_path):
    try:
        # Read the XML file
        xml_data = read_xml_file(xml_input_path)

        # Convert XML to OCDS format
        ocds_data = eform_to_ocds(xml_data)

        # Write the OCDS JSON to a file
        write_json_file(ocds_data, json_output_path)

        print(f"Successfully converted XML to JSON. Output saved in '{json_output_path}'")
    except Exception as e:
        print(f"An error occurred: {e}", file=sys.stderr)

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python script.py <input_path.xml> <output_path.json>")
    else:
        xml_input_path = sys.argv[1]
        json_output_path = sys.argv[2]
        main(xml_input_path, json_output_path)