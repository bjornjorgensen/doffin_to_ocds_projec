import unittest
from unittest.mock import MagicMock, patch
from src.mapper2 import convert_eform_to_ocds
from lxml import etree

class TestEformConverter(unittest.TestCase):
    def setUp(self):
        self.eform_xml = """<root>
            <!-- Your XML content goes here -->
        </root>"""
        self.root = etree.fromstring(self.eform_xml.encode('utf-8'))

    def test_map_legal_basis(self):
        # Mock the necessary XML nodes
        root_mock = MagicMock()

        # Mock nodes for BT-01(c)-Procedure Procedure Legal Basis (ID)
        legislation_doc_reference_mock_1 = MagicMock()
        id_node_mock_1 = MagicMock()
        id_node_mock_1.text = "http://data.europa.eu/eli/dir/2014/24/oj"
        legislation_doc_reference_mock_1.find.return_value = id_node_mock_1

        # Mock nodes for BT-01(d)-Procedure Procedure Legal Basis (Description)
        legislation_doc_reference_mock_2 = MagicMock()
        description_node_mock = MagicMock()
        description_node_mock.text = "Directive XYZ applies ..."
        legislation_doc_reference_mock_2.find.return_value = description_node_mock

        # Mock nodes for BT-01(e)-Procedure Procedure Legal Basis (NoID)
        legislation_doc_reference_mock_3 = MagicMock()
        id_node_mock_3 = MagicMock()
        id_node_mock_3.text = "LocalLegalBasis"
        legislation_doc_reference_mock_3.find.return_value = id_node_mock_3

        # Mock nodes for BT-01(f)-Procedure Procedure Legal Basis (NoID Description)
        legislation_doc_reference_mock_4 = MagicMock()
        description_node_mock_4 = MagicMock()
        description_node_mock_4.text = "Local legal basis description ..."
        legislation_doc_reference_mock_4.find.return_value = description_node_mock_4

        # Mock nodes for BT-01-notice * Procedure Legal Basis
        regulatory_domain_node_mock = MagicMock()
        regulatory_domain_node_mock.text = "32014L0024"

        root_mock.findall.return_value = [
            legislation_doc_reference_mock_1,
            legislation_doc_reference_mock_2,
            legislation_doc_reference_mock_3,
            legislation_doc_reference_mock_4
        ]
        root_mock.find.return_value = regulatory_domain_node_mock

        with patch('src.mapper2.etree.fromstring', return_value=root_mock):
            result = convert_eform_to_ocds(self.eform_xml)

            # Assert the expected output for BT-01(c)-Procedure Procedure Legal Basis (ID)
            self.assertEqual(result["tender"]["legalBasis"][0]["scheme"], "ELI")
            self.assertEqual(result["tender"]["legalBasis"][0]["id"], "http://data.europa.eu/eli/dir/2014/24/oj")

            # Assert the expected output for BT-01(d)-Procedure Procedure Legal Basis (Description)
            self.assertEqual(result["tender"]["legalBasis"][1]["description"], "Directive XYZ applies ...")

            # Assert the expected output for BT-01(e)-Procedure Procedure Legal Basis (NoID)
            self.assertEqual(result["tender"]["legalBasis"][2]["id"], "LocalLegalBasis")

            # Assert the expected output for BT-01(f)-Procedure Procedure Legal Basis (NoID Description)
            self.assertEqual(result["tender"]["legalBasis"][3]["description"], "Local legal basis description ...")

            # Assert the expected output for BT-01-notice * Procedure Legal Basis
            self.assertEqual(result["tender"]["legalBasis"][4]["scheme"], "CELEX")
            self.assertEqual(result["tender"]["legalBasis"][4]["id"], "32014L0024")

    def test_map_strategic_procurement(self):
        # Mock the necessary XML nodes and check if the function returns the correct output
        lot_node_mock = MagicMock()
        lot_node_mock.find.return_value.text = "Lot1"
        project_node_mock = MagicMock()
        additional_type_node_mock = MagicMock()
        additional_type_node_mock.find.return_value.text = "env-pur"
        project_node_mock.findall.return_value = [additional_type_node_mock]
        root_mock = MagicMock()
        root_mock.findall.return_value = [lot_node_mock]

        # Mock the issue date and issue time nodes with valid values
        issue_date_node_mock = MagicMock()
        issue_date_node_mock.text = "2023-04-20"
        issue_time_node_mock = MagicMock()
        issue_time_node_mock.text = "10:30:00"
        root_mock.find.side_effect = [issue_date_node_mock, issue_time_node_mock, None]

        # Mock the contract folder ID node
        contract_folder_id_node_mock = MagicMock()
        contract_folder_id_node_mock.text = "123456789"
        root_mock.find.side_effect.append(contract_folder_id_node_mock)

        expected_output = [{
            "lot": {"id": "Lot1", "hasSustainability": True},
            "sustainability": {
                "goal": "environmental",
                "strategies": ["awardCriteria", "contractPerformanceConditions", "selectionCriteria", "technicalSpecifications"]
            }
        }]

        with patch('src.mapper2.etree.fromstring', return_value=root_mock):
            result = convert_eform_to_ocds(self.eform_xml)
            self.assertEqual(result["tender"]["lots"], expected_output)
            self.assertEqual(result["tender"]["id"], "123456789")

        # Additional test case for BT-06-Lot Strategic Procurement
        additional_type_node_mock_2 = MagicMock()
        additional_type_node_mock_2.find.return_value.text = "none"
        project_node_mock.findall.return_value = [additional_type_node_mock, additional_type_node_mock_2]

        expected_output_2 = [{
            "lot": {"id": "Lot1", "hasSustainability": True},
            "sustainability": {
                "goal": "environmental",
                "strategies": ["awardCriteria", "contractPerformanceConditions", "selectionCriteria", "technicalSpecifications"]
            }
        }]

        with patch('src.mapper2.etree.fromstring', return_value=root_mock):
            result = convert_eform_to_ocds(self.eform_xml)
            self.assertEqual(result["tender"]["lots"], expected_output_2)

    def test_map_contracting_parties(self):
        # Mock the necessary XML nodes and check if the function returns the correct output
        root_mock = MagicMock()

        # Mock nodes for BT-10-Procedure-Buyer * Activity Authority
        party_mock = MagicMock()
        party_id_node_mock = MagicMock()
        party_id_node_mock.text = "ORG-0001"
        party_mock.find.return_value = party_id_node_mock
        contracting_activity_mock = MagicMock()
        activity_type_code_node_mock = MagicMock()
        activity_type_code_node_mock.text = "gas-oil"
        activity_type_code_node_mock.get.return_value = "http://example.com/eu-main-activity"
        contracting_activity_mock.find.return_value = activity_type_code_node_mock
        contracting_party_mock = MagicMock()
        contracting_party_mock.find.side_effect = [party_mock, contracting_activity_mock]
        root_mock.findall.return_value = [contracting_party_mock]

        # Mock nodes for BT-11-Procedure-Buyer * Buyer Legal Type
        party_type_code_node_mock = MagicMock()
        party_type_code_node_mock.text = "body-pl"
        party_type_code_node_mock.get.return_value = "buyer-legal-type"
        contracting_party_type_mock = MagicMock()
        contracting_party_type_mock.find.return_value = party_type_code_node_mock
        contracting_party_mock.find.side_effect.append(contracting_party_type_mock)

        expected_output = [
            {
                "id": "ORG-0001",
                "details": {
                    "classifications": [
                        {
                            "scheme": "eu-main-activity",
                            "id": "gas-oil",
                            "description": "Activities related to the exploitation of a geographical area for the purpose of extracting oil or gas."
                        },
                        {
                            "scheme": "TED_CA_TYPE",
                            "id": "body-pl",
                            "description": "Body governed by public law."
                        }
                    ]
                }
            }
        ]

        with patch('src.mapper2.etree.fromstring', return_value=root_mock):
            result = convert_eform_to_ocds(self.eform_xml)
            self.assertEqual(result["parties"], expected_output)

    def test_bt_01c_procedure_legal_basis_id(self):
        # Mock the necessary XML nodes
        root_mock = MagicMock()
        legislation_doc_reference_mock = MagicMock()
        id_node_mock = MagicMock()
        id_node_mock.text = "http://data.europa.eu/eli/dir/2014/24/oj"
        legislation_doc_reference_mock.find.return_value = id_node_mock
        root_mock.findall.return_value = [legislation_doc_reference_mock]

        with patch('src.mapper2.etree.fromstring', return_value=root_mock):
            result = convert_eform_to_ocds(self.eform_xml)
            self.assertEqual(result["tender"]["legalBasis"]["scheme"], "ELI")
            self.assertEqual(result["tender"]["legalBasis"]["id"], "http://data.europa.eu/eli/dir/2014/24/oj")

    def test_bt_01d_procedure_legal_basis_description(self):
        # Mock the necessary XML nodes
        root_mock = MagicMock()
        legislation_doc_reference_mock = MagicMock()
        description_node_mock = MagicMock()
        description_node_mock.text = "Directive XYZ applies ..."
        legislation_doc_reference_mock.find.return_value = description_node_mock
        root_mock.findall.return_value = [legislation_doc_reference_mock]

        with patch('src.mapper2.etree.fromstring', return_value=root_mock):
            result = convert_eform_to_ocds(self.eform_xml)
            self.assertEqual(result["tender"]["legalBasis"]["description"], "Directive XYZ applies ...")
    
    def test_bt_124_part_tool_atypical_url(self):
        # Mock the necessary XML nodes
        root_mock = MagicMock()
        lot_node_mock = MagicMock()
        lot_id_node_mock = MagicMock()
        lot_id_node_mock.text = "PAR-0001"
        lot_id_node_mock.get.return_value = "Part"
        lot_node_mock.find.return_value = lot_id_node_mock
        access_tools_uri_node_mock = MagicMock()
        access_tools_uri_node_mock.text = "https://my-atypical-tool.com/"
        lot_node_mock.find.return_value = access_tools_uri_node_mock
        root_mock.findall.return_value = [lot_node_mock]

        with patch('src.mapper2.etree.fromstring', return_value=root_mock):
            result = convert_eform_to_ocds(self.eform_xml)
            self.assertEqual(result["tender"]["communication"]["atypicalToolUrl"], "https://my-atypical-tool.com/") 

    

if __name__ == "__main__":
    unittest.main()