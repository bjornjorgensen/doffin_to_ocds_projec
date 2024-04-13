# tests/test_mapper3.py
import unittest
from src.mapper3 import eform_to_ocds, lookup_form_type # Adjust the import path as necessary
from xml.etree import ElementTree as etree

class TestEFormToOCDSIntegration(unittest.TestCase):
    def create_test_eform(self, scheme, id_value, description=None):
        """
        Builds the XML string dynamically based on input parameters,
        allowing for the creation of custom eForm XML for testing purposes.
        """
        description_xml = f'<cbc:DocumentDescription languageID="ENG">{description}</cbc:DocumentDescription>' if description else ''
        return f"""
                <root xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
                    xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
                <cac:TenderingTerms>
                    <cac:ProcurementLegislationDocumentReference>
                    <cbc:ID schemeName="{scheme}">{id_value}</cbc:ID>
                    {description_xml}
                    </cac:ProcurementLegislationDocumentReference>
                </cac:TenderingTerms>
                </root>
                """

    def test_BT_01c_Procedure(self):
        """Tests conversion of ELI legal basis with a scheme and ID."""
        scheme = "ELI"
        id_value = "http://data.europa.eu/eli/dir/2014/24/oj"

        test_eform = self.create_test_eform(scheme, id_value)

        expected_ocds = {
            "tender": {
                "legalBasis": {
                    "scheme": scheme,
                    "id": id_value,
                }
            }
        }

        result = eform_to_ocds(test_eform, lookup_form_type)

        self.assertEqual(result, expected_ocds)

    def test_BT_01d_Procedure(self):
        """Tests conversion of legal basis with scheme, ID, and description."""
        scheme = "Directive"
        id_value = "2004/18/EC"
        description = "Directive 2004/18/EC of the European Parliament and of the Council of 31 March 2004"

        test_eform = self.create_test_eform(scheme, id_value, description)

        expected_ocds = {
            "tender": {
                "legalBasis": {
                    "id": id_value,
                    "scheme": scheme,
                    "description": description,
                }
            }
        }

        result = eform_to_ocds(test_eform, lookup_form_type)

        self.assertEqual(result, expected_ocds)

    def test_BT_01e_Procedure_NoID(self):
        """Tests conversion of legal basis with a specific ID indicating a local legal basis."""
        eform_xml = """
            <root xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
                xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
            <cac:TenderingTerms>
                <cac:ProcurementLegislationDocumentReference>
                <cbc:ID>LocalLegalBasis</cbc:ID>
                </cac:ProcurementLegislationDocumentReference>
            </cac:TenderingTerms>
            </root>
            """

        expected_output = {
            "tender": {
                "legalBasis": {
                    "id": "LocalLegalBasis"
                }
            }
        }

        result = eform_to_ocds(eform_xml, lookup_form_type)

        self.assertEqual(result, expected_output)


    def test_BT_01f_Procedure_NoID_Description(self):
            """
            Tests conversion of legal basis with 'LocalLegalBasis' as the ID and
            specifically checks the handling of the legal basis description in the absence of a standard ID.
            """
            eform_xml = """
            <root xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
                xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
            <cac:TenderingTerms>
                <cac:ProcurementLegislationDocumentReference>
                <cbc:ID>LocalLegalBasis</cbc:ID>
                <cbc:DocumentDescription languageID="ENG">Directive XYZ applies ...</cbc:DocumentDescription>
                </cac:ProcurementLegislationDocumentReference>
            </cac:TenderingTerms>
            </root>
            """

            expected_output = {
                "tender": {
                    "legalBasis": {
                        "description": "Directive XYZ applies ..."
                    }
                }
            }

            result = eform_to_ocds(eform_xml, lookup_form_type)

            self.assertEqual(result, expected_output)

    def test_BT_01_RegulatoryDomain_CELEX(self):
        """
        Tests conversion of cbc:RegulatoryDomain to tender.legalBasis with CELEX scheme.
        """
        eform_xml = """
        <root xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
        <cbc:RegulatoryDomain>32014L0024</cbc:RegulatoryDomain>
        </root>
        """
        expected_output = {
            "tender": {
                "legalBasis": {
                    "scheme": "CELEX",
                    "id": "32014L0024"
                }
            }
        }
        result = eform_to_ocds(eform_xml, lookup_form_type)
        self.assertEqual(result, expected_output)

    def test_BT_01f_Procedure_LegalBasis_NoID_Description(self):
        """
        Tests the mapping for a legal basis described with a 'LocalLegalBasis' as the ID
        and a specific description, without a standard ID but with a description. This tests
        checks if the description is properly captured in tender.legalBasis.description.
        """
        eform_xml = """
        <root xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
        xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
        <cac:TenderingTerms>
        <cac:ProcurementLegislationDocumentReference>
        <cbc:ID>LocalLegalBasis</cbc:ID>
        <cbc:DocumentDescription languageID="ENG">Directive XYZ applies ...</cbc:DocumentDescription>
        </cac:ProcurementLegislationDocumentReference>
        </cac:TenderingTerms>
        </root>
        """
        expected_output = {
            "tender": {
                "legalBasis": {
                    "description": "Directive XYZ applies ..."
                }
            }
        }
        result = eform_to_ocds(eform_xml, lookup_form_type)
        self.assertEqual(result, expected_output)

    
    def test_BT_02_Notice_NoticeTypeCode_Discard(self):
        """
        Tests that the NoticeTypeCode is effectively discarded from the output,
        in line with the mapping requirement for BT-02.
        """
        eform_xml = """
        <root xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
        <cbc:NoticeTypeCode>veat</cbc:NoticeTypeCode>
        </root>
        """
        # The expected output does not contain the NoticeTypeCode, since it's discarded.
        expected_output = {
            # Assuming the base structure after processing. It can vary depending on your actual output requirements.
        }
        result = eform_to_ocds(eform_xml, lookup_form_type)
        # Assert that NoticeTypeCode is not in the result, showing it's effectively discarded.
        # This checks the absence of 'noticeType' or similar fields in the result.
        self.assertNotIn('noticeType', result, "NoticeTypeCode should be discarded and not present in the output.")

        # Optional: Additional assertions can be added to verify the structure of `result`
        # or other fields if needed, based on what the `eform_to_ocds` function returns.

    def test_BT_01_notice_Procedure_Legal_Basis(self):
        xml_input = """
        <root xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
        <cbc:RegulatoryDomain>32014L0024</cbc:RegulatoryDomain>
        </root>
        """
        expected_output = {
            "tender": {
                "legalBasis": {
                    "scheme": "CELEX",
                    "id": "32014L0024"
                }
            }
        }

        ocds_output = eform_to_ocds(xml_input, lookup_form_type)
        assert ocds_output == expected_output, "The mapping for Procedure Legal Basis (BT-01) failed."

    def test_BT_03_notice_Form_Type(self):
        xml_input = """
        <root xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
            <cbc:NoticeTypeCode listName="competition">cn-standard</cbc:NoticeTypeCode>
        </root>
        """
        expected_output = {
            "tag": ["tender"],
            "tender": {"status": "active"}
        }

        # Assuming 'eform_to_ocds' is your implementation function
        ocds_output = eform_to_ocds(xml_input, lookup_form_type)
        
        assert ocds_output == expected_output, "The BT-03 mapping did not produce the expected OCDS output."

    def test_BT_04_notice_Procedure_Identifier(self):
        # Sample XML input with a ContractFolderID element
        xml_input = """
        <root xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
            <cbc:ContractFolderID>1e86a664-ae3c-41eb-8529-0242ac130003</cbc:ContractFolderID>
        </root>
        """
        # Expected OCDS JSON output where tender.id matches the ContractFolderID value
        expected_output = {
            "tender": { "id": "1e86a664-ae3c-41eb-8529-0242ac130003" }
        }

        # Applying the transformation function
        ocds_output = eform_to_ocds(xml_input, lookup_form_type)
        
        # Assertion to validate the outcome matches expectations
        assert ocds_output == expected_output, "The BT-04 mapping did not produce the expected OCDS output."

    def test_BT_05_notice_Dispatch_Date(self):
        eform_xml = '''
        <root xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
              xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
            <cbc:IssueDate>2019-11-26</cbc:IssueDate>
            <cbc:IssueTime>13:38:54+01:00</cbc:IssueTime>
        </root>
        '''
        expected_output = {
            "date": "2019-11-26T13:38:54+01:00"
        }
        result = eform_to_ocds(eform_xml, lookup_form_type)
        self.assertEqual(result, expected_output)

    def test_BT_01f_Procedure_LegalBasis_NoID_Description(self):
        eform_xml = '''
            <root xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
                xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
            <cac:TenderingTerms>
            <cac:ProcurementLegislationDocumentReference>
                <cbc:ID schemeName="Directive">LocalLegalBasis</cbc:ID>
                <cbc:DocumentDescription languageID="ENG">Directive XYZ applies ...</cbc:DocumentDescription>
            </cac:ProcurementLegislationDocumentReference>
            </cac:TenderingTerms>
        </root>
        '''
        expected_output = {
            "tender": {
                "legalBasis": {
                    "description": "Directive XYZ applies ..."
                }
            }
        }
        result = eform_to_ocds(eform_xml, lookup_form_type)
        self.assertEqual(result, expected_output)

    
    def test_BT_02_Notice_NoticeTypeCode_Discard(self):
        eform_xml = '''
        <root xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
            <cbc:NoticeTypeCode listName="competition">veat</cbc:NoticeTypeCode>
        </root>
         '''
        expected_output = {
            "tag": ["tender"],
            "tender": {"status": "active"}
        }
        result = eform_to_ocds(eform_xml, lookup_form_type)
        self.assertEqual(result, expected_output, "The BT-03 mapping should utilize listName but BT-02 should discard the content 'veat'")

    def test_BT_03_notice_Form_Type(self):
        eform_xml = '''
        <root xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
            <cbc:NoticeTypeCode listName="competition">cn-standard</cbc:NoticeTypeCode>
        </root>
            '''
        expected_output = {
            "tag": ["tender"],
            "tender": {"status": "active"}
        }
        result = eform_to_ocds(eform_xml, lookup_form_type)
        self.assertEqual(result, expected_output, "BT-03 mapping should properly set the tag and tender status based on the listName attribute")

    def test_BT_03_form_type(self):
        # XML input with a NoticeTypeCode element and listName attribute
        xml_input = """
        <root xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
            <cbc:NoticeTypeCode listName="competition">cn-standard</cbc:NoticeTypeCode>
        </root>
        """
        # Expected JSON output determined by the listName mapping
        expected_output = {
            "tag": ["tender"],
            "tender": {"status": "active"}
        }

        # Execute the mapping function with the provided XML input
        ocds_output = eform_to_ocds(xml_input, lookup_form_type)
        
        # Assert that the actual output matches the expected output
        assert ocds_output == expected_output, "BT-03 Test Failed: The mapping for NoticeTypeCode[@listName='competition'] did not produce the expected result."
        
    def test_dispatch_date_time(self):
        # XML input simulating the eForm structure with IssueDate and IssueTime
        eform_xml = '''
        <root xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
            <cbc:IssueDate>2019-11-26</cbc:IssueDate>
            <cbc:IssueTime>13:38:54+01:00</cbc:IssueTime>
        </root>
        '''
        expected_output = {
            "date": "2019-11-26T13:38:54+01:00"
        }
        result = eform_to_ocds(eform_xml, lookup_form_type)
        self.assertEqual(result, expected_output, "The dispatch date and time were not processed correctly")    


class TestLotStrategicProcurement(unittest.TestCase):
    def test_BT_06_lot_strategic_procurement(self):
        eform_xml = '''
            <root xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
                  xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
                <cac:ProcurementProjectLot>
                    <cbc:ID schemeName="Lot">LOT-0001</cbc:ID>
                    <cac:ProcurementProject>
                        <cac:ProcurementAdditionalType>
                            <cbc:ProcurementTypeCode listName="strategic-procurement">inn-pur</cbc:ProcurementTypeCode>
                        </cac:ProcurementAdditionalType>
                    </cac:ProcurementProject>
                </cac:ProcurementProjectLot>
                <cac:ProcurementProjectLot>
                    <cbc:ID schemeName="Lot">LOT-0002</cbc:ID>
                    <cac:ProcurementProject>
                        <cac:ProcurementAdditionalType>
                            <cbc:ProcurementTypeCode listName="strategic-procurement">none</cbc:ProcurementTypeCode>
                        </cac:ProcurementAdditionalType>
                    </cac:ProcurementProject>
                </cac:ProcurementProjectLot>
            </root>
        '''

        expected_output = {
            'tender': {
                'lots': [
                    {
                        'id': 'LOT-0001',
                        'hasSustainability': True,
                        'sustainability': [
                            {
                                'goal': 'economic.innovativePurchase',
                                'strategies': [
                                    'awardCriteria',
                                    'contractPerformanceConditions',
                                    'selectionCriteria',
                                    'technicalSpecifications'
                                ]
                            }
                        ]
                    },
                    {
                        'id': 'LOT-0002',
                        'hasSustainability': False,
                        'sustainability': []
                    }
                ]
            }
        }

        result = eform_to_ocds(eform_xml, lookup_form_type)
        self.assertEqual(result, expected_output)


    def test_cross_border_law(self):
        # A minimal eForm XML sample containing the CrossBorderLaw description
        eform_xml = """
        <Root xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
              xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
            <cac:TenderingTerms>
                <cac:ProcurementLegislationDocumentReference>
                    <cbc:ID>CrossBorderLaw</cbc:ID>
                    <cbc:DocumentDescription>Directive XYZ on Cross Border Procurement</cbc:DocumentDescription>
                </cac:ProcurementLegislationDocumentReference>
            </cac:TenderingTerms>
        </Root>
        """

       # Convert the eForm XML to OCDS data directly using the XML string
        ocds_data = eform_to_ocds(eform_xml, lookup_form_type)
        
        # Assert checks
        expected_cross_border_law = "Directive XYZ on Cross Border Procurement"
        # Check if your ocds_data structure places 'crossBorderLaw' inside 'tender' or directly at the root or another structure
        self.assertIn('tender', ocds_data, "The 'tender' key should exist in OCDS data.")
        self.assertIn('crossBorderLaw', ocds_data['tender'], "The 'crossBorderLaw' key should exist in the tender data.")
        self.assertEqual(ocds_data['tender']['crossBorderLaw'], expected_cross_border_law,
                         "The crossBorderLaw should match the expected description.")

    def test_buyer_activity(self):
        # A minimal eForm XML sample containing the buyer's activity information 
        eform_xml = """
        <Root xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
        xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
        <cac:ContractingParty>
            <cac:ContractingActivity>
                <cbc:ActivityTypeCode listName="BuyerActivityList">ActivityCode123</cbc:ActivityTypeCode>
            </cac:ContractingActivity>
        </cac:ContractingParty>
        </Root>
        """
        # Convert the eForm XML to OCDS data directly using the XML string
        ocds_data = eform_to_ocds(eform_xml, lookup_form_type)

        # Assert checks
        expected_buyer_activity = {
            "scheme": "eu-main-activity",
            "id": "ActivityCode123",
            "description": "ActivityCode123"  # Placeholder for the actual description, adjust as necessary
        }

        # Check if your ocds_data structure places 'parties' and looks for the specific classification within the appropriate party
        self.assertIn('parties', ocds_data, "The 'parties' key should exist in OCDS data.")

        found_activity_classification = any(
            expected_buyer_activity in party.get("details", {}).get("classifications", [])
            for party in ocds_data['parties']
        )
        
        self.assertTrue(found_activity_classification,
                        "The expected buyer activity classification should exist within the parties' classifications.")

    def test_procedure_type(self):
        # A minimal eForm XML sample containing the procedure type information
        eform_xml = """
            <Root xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
                  xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
                <cac:TenderingProcess>
                    <cbc:ProcedureCode listName="procurement-procedure-type">open</cbc:ProcedureCode>
                </cac:TenderingProcess>
            </Root>
        """
        # Convert the eForm XML to OCDS data directly using the XML string
        ocds_data = eform_to_ocds(eform_xml, lookup_form_type)

        # Assert checks
        expected_procedure_data = {
            "procurementMethod": "open",
            "procurementMethodDetails": "Open procedure"
        }

        # Check if your ocds_data structure places 'tender' and contains the expected procedure data
        self.assertIn('tender', ocds_data, "The 'tender' key should exist in OCDS data.")
        for key, value in expected_procedure_data.items():
            self.assertIn(key, ocds_data['tender'], f"The '{key}' key should exist in the tender object.")
            self.assertEqual(ocds_data['tender'][key], value, f"The '{key}' value does not match the expected value.")

    def test_procedure_type_not_found(self):
        # A minimal eForm XML sample without the procedure type information
        eform_xml = """
            <Root xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
                  xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
                <cac:TenderingProcess>
                    <!-- No ProcedureCode element -->
                </cac:TenderingProcess>
            </Root>
        """
        # Convert the eForm XML to OCDS data directly using the XML string
        ocds_data = eform_to_ocds(eform_xml, lookup_form_type)

        # Assert checks
        self.assertNotIn('procurementMethod', ocds_data.get('tender', {}), "The 'procurementMethod' key should not exist in the tender object.")
        self.assertNotIn('procurementMethodDetails', ocds_data.get('tender', {}), "The 'procurementMethodDetails' key should not exist in the tender object.")

    def test_accelerated_procedure_not_found(self):
        # A minimal eForm XML sample without the accelerated procedure information
        eform_xml = """
            <Root xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
                  xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
                <cac:TenderingProcess>
                    <!-- No ProcessJustification element for accelerated procedure -->
                </cac:TenderingProcess>
            </Root>
        """
        # Convert the eForm XML to OCDS data directly using the XML string
        ocds_data = eform_to_ocds(eform_xml, lookup_form_type)

        # Assert checks that the 'procedure' key does not contain the 'isAccelerated' key when the accelerated procedure is not mentioned in the XML
        self.assertNotIn('procedure', ocds_data.get('tender', {}), "The 'procedure' key should not exist if there is no accelerated procedure information.")
        if 'procedure' in ocds_data.get('tender', {}):
            self.assertNotIn('isAccelerated', ocds_data['tender']['procedure'], "The 'isAccelerated' key should not exist in the procedure object.")

    def test_framework_duration_justification_present(self):
        # XML input where Framework Agreement Justification is provided
        eform_xml = """
            <Root xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
                  xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
                <cac:ProcurementProjectLot>
                    <cbc:ID schemeName="Lot">1</cbc:ID>
                    <cac:TenderingProcess>
                        <cac:FrameworkAgreement>
                            <cbc:Justification>Required due to extended project scope</cbc:Justification>
                        </cac:FrameworkAgreement>
                    </cac:TenderingProcess>
                </cac:ProcurementProjectLot>
            </Root>
        """
        ocds_data = eform_to_ocds(eform_xml, lookup_form_type)

        # Assert the lot contains the correct framework agreement justification
        self.assertTrue('lots' in ocds_data['tender'], "Lots should be present in the OCDS data.")
        self.assertTrue('techniques' in ocds_data['tender']['lots'][0], "Techniques data should be present in the lot.")
        self.assertEqual(
            ocds_data['tender']['lots'][0]['techniques']['frameworkAgreement']['periodRationale'],
            "Required due to extended project scope",
            "The period rationale should match the provided justification."
        )

    def test_framework_duration_justification_absent(self):
        # XML input without Framework Agreement Justification
        eform_xml = """
            <Root xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
                  xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
                <cac:ProcurementProjectLot>
                    <cbc:ID schemeName="Lot">1</cbc:ID>
                    <cac:TenderingProcess>
                        <cac:FrameworkAgreement>
                            <!-- No Justification Element -->
                        </cac:FrameworkAgreement>
                    </cac:TenderingProcess>
                </cac:ProcurementProjectLot>
            </Root>
        """
        ocds_data = eform_to_ocds(eform_xml, lookup_form_type)

        # Assert techniques or frameworkAgreement keys should not be present if there's no justification
        self.assertTrue('lots' in ocds_data['tender'], "Lots should be present in the OCDS data.")
        self.assertTrue('techniques' not in ocds_data['tender']['lots'][0] or 'frameworkAgreement' not in ocds_data['tender']['lots'][0]['techniques'],
                        "Framework agreement or its justification should not be present if not provided in the XML.")
        
    def test_cross_border_law_present(self):
        # XML with cross-border law described
        eform_xml = """
            <Root xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
                  xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
                <cac:TenderingTerms>
                    <cac:ProcurementLegislationDocumentReference>
                        <cbc:ID>CrossBorderLaw</cbc:ID>
                        <cbc:DocumentDescription>Directive XYZ on Cross Border Procurement</cbc:DocumentDescription>
                    </cac:ProcurementLegislationDocumentReference>
                </cac:TenderingTerms>
            </Root>
        """
        ocds_data = eform_to_ocds(eform_xml, lookup_form_type)
        self.assertEqual(ocds_data['tender']['crossBorderLaw'], "Directive XYZ on Cross Border Procurement", "Cross Border Law should be correctly extracted")

    def test_cross_border_law_absent(self):
        # XML without cross-border law description
        eform_xml = """
            <Root xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
                  xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
                <cac:TenderingTerms>
                    <!-- No CrossBorderLaw DocumentReference -->
                </cac:TenderingTerms>
            </Root>
        """
        ocds_data = eform_to_ocds(eform_xml, lookup_form_type)
        self.assertNotIn('crossBorderLaw', ocds_data.get('tender', {}), "Cross Border Law should not be present if not provided")

    def test_buyer_legal_type_extraction(self):
        eform_xml = """
            <Root xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
                  xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
                <cac:ContractingParty>
                    <cac:Party>
                        <cac:PartyIdentification>
                            <cbc:ID schemeName="organization">ORG-0001</cbc:ID>
                        </cac:PartyIdentification>
                    </cac:Party>
                    <cac:ContractingPartyType>
                        <cbc:PartyTypeCode listName="buyer-legal-type">body-pl</cbc:PartyTypeCode>
                    </cac:ContractingPartyType>
                </cac:ContractingParty>
            </Root>
        """
        # Convert the eForm XML to OCDS data directly using the XML string
        ocds_data = eform_to_ocds(eform_xml, lookup_form_type)

        # Assert checks that the parties are correctly extracted with legal type information
        expected_classification = {
            "scheme": "TED_CA_TYPE",
            "id": "body-pl",
            "description": "Body governed by public law"
        }
        self.assertIn('parties', ocds_data, "Parties data should be present in the OCDS data.")
        self.assertTrue(isinstance(ocds_data['parties'], list), "Parties should be a list.")
        self.assertTrue(len(ocds_data['parties']) > 0, "Parties list should not be empty.")
        self.assertIn('classifications', ocds_data['parties'][0].get('details', {}), "Classifications should exist in parties[0].details.")
        self.assertEqual(ocds_data['parties'][0]['details']['classifications'][0], expected_classification, 
                         "The classification data of the buyer should match the expected values.")

    
    def test_buyer_categories_integration(self):
        eform_xml = """
        <Root xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
              xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
            <cac:ContractingParty>
                <cac:Party>
                    <cac:PartyIdentification>
                        <cbc:ID schemeName="organization">ORG-0023</cbc:ID>
                    </cac:PartyIdentification>
                </cac:Party>
                <cac:ContractingPartyType>
                    <cbc:PartyTypeCode listName="buyer-legal-type">central-gov</cbc:PartyTypeCode>
                </cac:ContractingPartyType>
            </cac:ContractingParty>
            <cac:ProcurementProjectLot>
                <cbc:ID schemeName="Lot">LOT-0001</cbc:ID>
                <cac:TenderingProcess>
                    <cac:FrameworkAgreement>
                        <cac:SubsequentProcessTenderRequirement>
                            <cbc:Name>buyer-categories</cbc:Name>
                            <cbc:Description>Offices of the "greater region"</cbc:Description>
                        </cac:SubsequentProcessTenderRequirement>
                    </cac:FrameworkAgreement>
                </cac:TenderingProcess>
            </cac:ProcurementProjectLot>
        </Root>
        """
        
        # Define a namespace dictionary
        ns = {
            'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
            'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2'
        }

        root = etree.fromstring(eform_xml)
        ocds_data = eform_to_ocds(eform_xml, lookup_form_type)

        expected_classification = {
            "scheme": "TED_CA_TYPE",
            "id": "central-gov",
            "description": "Central government authority"
        }

        # Test if parties are created and legal type is classified correctly
        self.assertIn('parties', ocds_data, "Parties data should be present in the OCDS data.")
        self.assertEqual(ocds_data['parties'][0]['details']['classifications'][0], expected_classification,
                         "The classification data should match expected values.")

        # Test to ensure the buyer categories are correctly integrated into the lot structure
        expected_buyer_categories = "Offices of the \"greater region\""
        self.assertEqual(len(ocds_data['tender']['lots']), 1, "There should be exactly one lot parsed.")
        self.assertIn('techniques', ocds_data['tender']['lots'][0], "Techniques should be present in the lot data.")
        self.assertIn('frameworkAgreement', ocds_data['tender']['lots'][0]['techniques'], "frameworkAgreement should be present under techniques.")
        self.assertEqual(ocds_data['tender']['lots'][0]['techniques']['frameworkAgreement']['buyerCategories'],
                         expected_buyer_categories, "Buyer categories should match the expected description.")
            
if __name__ == '__main__':
    unittest.main()

