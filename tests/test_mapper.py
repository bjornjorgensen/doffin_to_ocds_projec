import unittest
from pathlib import Path
from src.utility import extract_legal_basis  # Adjust import path as necessary

class TestUtilityFunctions(unittest.TestCase):

    def test_extract_legal_basis(self):
        # This test focuses on the basic functionality without the description
        sample_xml_path = Path("tests/data/sample_notice.xml")
        
        expected_output = {
            "scheme": "ELI",
            "id": "http://data.europa.eu/eli/dir/2014/24/oj"
            # Note: No description expected in this test case
        }
        
        result = extract_legal_basis(str(sample_xml_path))
        
        # Ensure it matches expected output, not expecting a description here
        self.assertDictEqual(result, expected_output)

    def test_extract_legal_basis_with_description(self):
        # This test extends to include the 'description'
        sample_xml_path = Path("tests/data/sample_notice_with_description.xml")
        
        expected_output = {
            "scheme": "ELI",
            "id": "http://data.europa.eu/eli/dir/2014/24/oj",
            "description": "Directive XYZ applies ..."  # Specific to this test
        }
        
        result = extract_legal_basis(str(sample_xml_path))
        
        # Ensure it matches the expected output fully, including the description
        self.assertDictEqual(result, expected_output)

if __name__ == "__main__":
    unittest.main()