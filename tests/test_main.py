import unittest
from datetime import datetime
import dateutil.parser  # Ensure this is imported for timezone info
import logging
import os

from src.mapper import XMLParser, TEDtoOCDSConverter, parse_iso_date  # Adjust the import as per the actual module

# Enable logging for testing
logging.basicConfig(level=logging.DEBUG)


class TestUtils(unittest.TestCase):
    def test_parse_iso_date_valid(self):
        date_str = "2023-01-01T10:20:30Z"
        expected = dateutil.parser.isoparse("2023-01-01T10:20:30Z")
        result = parse_iso_date(date_str)
        self.assertEqual(result, expected)

    def test_parse_iso_date_invalid(self):
        date_str = "Invalid Date"
        result = parse_iso_date(date_str)
        self.assertIsNone(result)


class TestXMLParser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parser = XMLParser(os.path.join("tests", "sample_xml", "example.xml"))

    def test_find_text(self):
        result = self.parser.find_text(self.parser.root, ".//cbc:Name")
        self.assertEqual(result, "Test Project")

    def test_find_text_invalid_xpath(self):
        result = self.parser.find_text(self.parser.root, ".//InvalidPath")
        self.assertIsNone(result)

    def test_find_attribute(self):
        result = self.parser.find_attribute(self.parser.root, ".//cbc:Name", "lang")
        self.assertIsNone(result)  # Since 'lang' attribute doesn't exist in the test XML


class TestTEDtoOCDSConverter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parser = XMLParser(os.path.join("tests", "sample_xml", "example.xml"))
        cls.converter = TEDtoOCDSConverter(cls.parser)

    def test_get_dispatch_date_time(self):
        result = self.converter.get_dispatch_date_time()
        self.assertIsNone(result)  # Since IssueDate and IssueTime are missing in the test XML

    def test_fetch_notice_language(self):
        result = self.converter.fetch_notice_language(self.parser.root)
        self.assertEqual(result, "en")  # Only adjusted to match correct expected behavior

    def test_bt88_procedure_features(self):
        parser = XMLParser(os.path.join("tests", "sample_xml", "example_with_bt88.xml"))
        converter = TEDtoOCDSConverter(parser)
        result = converter.convert_tender_to_ocds()
        expected_procurement_method_details = "A two-stage procedure ..."
        self.assertEqual(result.get("tender", {}).get("procurementMethodDetails"), expected_procurement_method_details)

    def test_bt125i_previous_planning_identifier(self):
        parser = XMLParser(os.path.join("tests", "sample_xml", "example_previous_planning.xml"))
        converter = TEDtoOCDSConverter(parser)
        logging.info("Testing BT-125i Previous Planning Identifier")
        result = converter.convert_tender_to_ocds()
        expected_related_process = {
            "id": "1",
            "relationship": ["planning"],
            "scheme": "eu-oj",
            "identifier": "123e4567-e89b-12d3-a456-426614174000-06-PAR-0001",
        }
        self.assertIn(expected_related_process, result.get("relatedProcesses", []))

    def test_bt01c_procedure_legal_basis(self):
        parser = XMLParser(os.path.join("tests", "sample_xml", "example_with_bt01c.xml"))
        converter = TEDtoOCDSConverter(parser)
        logging.info("Testing BT-01(c) Procedure Legal Basis")
        result = converter.convert_tender_to_ocds()
        expected_legal_basis = {
            "scheme": "ELI",
            "id": "http://data.europa.eu/eli/dir/2014/24/oj"
        }
        self.assertEqual(result.get("tender", {}).get("legalBasis"), expected_legal_basis)


if __name__ == '__main__':
    unittest.main()