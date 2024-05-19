import unittest
import io
import json
import sys
import os

# Adjust the Python path to include the src directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from mapper import convert_ted_to_ocds

class TestTedToOcdsConversion(unittest.TestCase):
    def setUp(self):
        self.ted_xml = """<?xml version="1.0" encoding="UTF-8"?>
<!-- Based on https://ted.europa.eu/udl?uri=TED:NOTICE:40003-2020:TEXT:EN:HTML
But with the minimal amount of information while still valid
-->
<ContractAwardNotice xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2" xmlns="urn:oasis:names:specification:ubl:schema:xsd:ContractAwardNotice-2" xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2" xmlns:efac="http://data.europa.eu/p27/eforms-ubl-extension-aggregate-components/1" xmlns:efext="http://data.europa.eu/p27/eforms-ubl-extensions/1" xmlns:efbc="http://data.europa.eu/p27/eforms-ubl-extension-basic-components/1" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
	<ext:UBLExtensions>
		<ext:UBLExtension>
			<ext:ExtensionContent>
				<efext:EformsExtension>
					<efac:NoticeResult>
						<cbc:TotalAmount currencyID="EUR">390697.84</cbc:TotalAmount>
						<efac:LotResult>
							<cbc:ID schemeName="result">RES-0001</cbc:ID>
							<cbc:HigherTenderAmount currencyID="EUR">95414</cbc:HigherTenderAmount>
							<cbc:LowerTenderAmount currencyID="EUR">59299.64</cbc:LowerTenderAmount>
							<cbc:TenderResultCode listName="winner-selection-status">selec-w</cbc:TenderResultCode>
							<efac:LotTender>
								<cbc:ID schemeName="tender">TEN-0001</cbc:ID>
							</efac:LotTender>
							<efac:ReceivedSubmissionsStatistics>
								<efbc:StatisticsCode listName="received-submission-type">tenders</efbc:StatisticsCode>
								<efbc:StatisticsNumeric>3</efbc:StatisticsNumeric>
							</efac:ReceivedSubmissionsStatistics>
							<efac:SettledContract>
								<cbc:ID schemeName="contract">CON-0001</cbc:ID>
							</efac:SettledContract>
							<efac:TenderLot>
								<cbc:ID schemeName="Lot">LOT-0000</cbc:ID>
							</efac:TenderLot>
						</efac:LotResult>
						<efac:LotTender>
							<cbc:ID schemeName="tender">TEN-0001</cbc:ID>
							<cbc:RankCode>1</cbc:RankCode>
							<efbc:TenderRankedIndicator>true</efbc:TenderRankedIndicator>
							<cac:LegalMonetaryTotal>
								<cbc:PayableAmount currencyID="EUR">95414</cbc:PayableAmount>
							</cac:LegalMonetaryTotal>
							<efac:SubcontractingTerm>
								<efbc:TermCode listName="applicability">no</efbc:TermCode>
							</efac:SubcontractingTerm>
							<efac:TenderingParty>
								<cbc:ID schemeName="tendering-party">TPA-0001</cbc:ID>
							</efac:TenderingParty>
							<efac:TenderLot>
								<cbc:ID schemeName="Lot">LOT-0000</cbc:ID>
							</efac:TenderLot>
							<efac:TenderReference>
								<cbc:ID>PROJ DEF/2022-01</cbc:ID>
							</efac:TenderReference>
						</efac:LotTender>
						<efac:SettledContract>
							<cbc:ID schemeName="contract">CON-0001</cbc:ID>
							<cbc:IssueDate>2019-09-03+02:00</cbc:IssueDate>
							<cac:SignatoryParty>
								<cac:PartyIdentification>
									<cbc:ID schemeName="organization">ORG-0001</cbc:ID>
								</cac:PartyIdentification>
							</cac:SignatoryParty>
							<efac:ContractReference>
								<cbc:ID>SCN DEF:2020-12</cbc:ID>
							</efac:ContractReference>
							<efac:LotTender>
								<cbc:ID schemeName="tender">TEN-0001</cbc:ID>
							</efac:LotTender>
						</efac:SettledContract>
						<efac:TenderingParty>
							<cbc:ID schemeName="tendering-party">TPA-0001</cbc:ID>
							<efac:Tenderer>
								<cbc:ID schemeName="organization">ORG-0004</cbc:ID>
							</efac:Tenderer>
						</efac:TenderingParty>
					</efac:NoticeResult>
					<efac:NoticeSubType>
						<cbc:SubTypeCode listName="notice-subtype">29</cbc:SubTypeCode>
					</efac:NoticeSubType>
					<efac:Organizations>
						<efac:Organization>
							<efac:Company>
								<cac:PartyIdentification>
									<cbc:ID schemeName="organization">ORG-0001</cbc:ID>
								</cac:PartyIdentification>
								<cac:PartyName>
									<cbc:Name languageID="FRA">Rouen Habitat</cbc:Name>
								</cac:PartyName>
								<cac:PostalAddress>
									<cbc:CityName>Rouen Cedex 1</cbc:CityName>
									<cbc:PostalZone>ABC123</cbc:PostalZone>
									<cbc:CountrySubentityCode listName="nuts">FRD22</cbc:CountrySubentityCode>
									<cac:Country>
										<cbc:IdentificationCode listName="country">FRA</cbc:IdentificationCode>
									</cac:Country>
								</cac:PostalAddress>
								<cac:PartyLegalEntity>
									<cbc:CompanyID>123 456 789</cbc:CompanyID>
								</cac:PartyLegalEntity>
								<cac:Contact>
									<cbc:Telephone>+33 235156161</cbc:Telephone>
									<cbc:ElectronicMail>contact@rouenhabitat.fr</cbc:ElectronicMail>
								</cac:Contact>
							</efac:Company>
						</efac:Organization>
						<efac:Organization>
							<efac:Company>
								<cac:PartyIdentification>
									<cbc:ID schemeName="organization">ORG-0002</cbc:ID>
								</cac:PartyIdentification>
								<cac:PartyName>
									<cbc:Name languageID="FRA">Tribunal administratif de Rouen</cbc:Name>
								</cac:PartyName>
								<cac:PostalAddress>
									<cbc:CityName>Rouen</cbc:CityName>
									<cbc:PostalZone>ABC123</cbc:PostalZone>
									<cbc:CountrySubentityCode listName="nuts">FRD22</cbc:CountrySubentityCode>
									<cac:Country>
										<cbc:IdentificationCode listName="country">FRA</cbc:IdentificationCode>
									</cac:Country>
								</cac:PostalAddress>
								<cac:PartyLegalEntity>
									<cbc:CompanyID>321 654 789</cbc:CompanyID>
								</cac:PartyLegalEntity>
							</efac:Company>
						</efac:Organization>
						<efac:Organization>
							<efbc:ListedOnRegulatedMarketIndicator>false</efbc:ListedOnRegulatedMarketIndicator>
							<efac:UltimateBeneficialOwner>
								<cbc:ID schemeName="ubo">UBO-0001</cbc:ID>
							</efac:UltimateBeneficialOwner>
							<efac:Company>
								<efbc:CompanySizeCode listName="economic-operator-size">micro</efbc:CompanySizeCode>
								<cac:PartyIdentification>
									<cbc:ID schemeName="organization">ORG-0004</cbc:ID>
								</cac:PartyIdentification>
								<cac:PartyName>
									<cbc:Name languageID="FRA">Espaces Verts Lemire</cbc:Name>
								</cac:PartyName>
								<cac:PostalAddress>
									<cbc:CityName>Le Grand-Quevilly</cbc:CityName>
									<cbc:PostalZone>ABC123</cbc:PostalZone>
									<cbc:CountrySubentityCode listName="nuts">FRD22</cbc:CountrySubentityCode>
									<cac:Country>
										<cbc:IdentificationCode listName="country">FRA</cbc:IdentificationCode>
									</cac:Country>
								</cac:PostalAddress>
								<cac:PartyLegalEntity>
									<cbc:CompanyID>326 912 557</cbc:CompanyID>
								</cac:PartyLegalEntity>
								<cac:Contact>
									<cbc:Telephone>+33 2 35 67 82 82</cbc:Telephone>
									<cbc:ElectronicMail>contact@example.com</cbc:ElectronicMail>
								</cac:Contact>
							</efac:Company>
						</efac:Organization>
						<efac:UltimateBeneficialOwner>
							<cbc:ID schemeName="ubo">UBO-0001</cbc:ID>
							<efac:Nationality>
								<cbc:NationalityID>FRA</cbc:NationalityID>
							</efac:Nationality>
						</efac:UltimateBeneficialOwner>
					</efac:Organizations>
				</efext:EformsExtension>
			</ext:ExtensionContent>
		</ext:UBLExtension>
	</ext:UBLExtensions>
	<cbc:UBLVersionID>2.3</cbc:UBLVersionID>
	<cbc:CustomizationID>eforms-sdk-1.11</cbc:CustomizationID>
	<cbc:ID schemeName="notice-id">65667997-031a-4198-bd25-7225449ef479</cbc:ID>
	<cbc:ContractFolderID>022d0ef9-6338-42d9-afa4-a87709128061</cbc:ContractFolderID>
	<cbc:IssueDate>2019-10-23+01:00</cbc:IssueDate>
	<cbc:IssueTime>00:00:00+01:00</cbc:IssueTime>
	<cbc:VersionID>01</cbc:VersionID>
	<cbc:RegulatoryDomain>32014L0024</cbc:RegulatoryDomain>
	<cbc:NoticeTypeCode listName="result">can-standard</cbc:NoticeTypeCode>
	<cbc:NoticeLanguageCode>FRA</cbc:NoticeLanguageCode>
	<cac:ContractingParty>
		<cac:ContractingPartyType>
			<cbc:PartyTypeCode listName="buyer-legal-type">pub-undert-la</cbc:PartyTypeCode>
		</cac:ContractingPartyType>
		<cac:ContractingActivity>
			<cbc:ActivityTypeCode listName="authority-activity">hc-am</cbc:ActivityTypeCode>
		</cac:ContractingActivity>
		<cac:Party>
			<cac:PartyIdentification>
				<cbc:ID schemeName="organization">ORG-0001</cbc:ID>
			</cac:PartyIdentification>
		</cac:Party>
	</cac:ContractingParty>
	<cac:TenderingProcess>
		<cbc:ProcedureCode listName="procurement-procedure-type">open</cbc:ProcedureCode>
	</cac:TenderingProcess>
	<cac:ProcurementProject>
		<cbc:Name languageID="FRA">Service d'entretien de remise en état et de nettoyage des espaces verts</cbc:Name>
		<cbc:Description languageID="FRA">Service d'entretien de remise en état et de nettoyage des espaces verts.</cbc:Description>
		<cbc:ProcurementTypeCode listName="contract-nature">services</cbc:ProcurementTypeCode>
		<cac:MainCommodityClassification>
			<cbc:ItemClassificationCode listName="cpv">77310000</cbc:ItemClassificationCode>
		</cac:MainCommodityClassification>
	</cac:ProcurementProject>
	<cac:ProcurementProjectLot>
		<cbc:ID schemeName="Lot">LOT-0000</cbc:ID>
		<cac:TenderingTerms>
			<cbc:FundingProgramCode listName="eu-funded">eu-funds</cbc:FundingProgramCode>
			<cac:AwardingTerms>
				<cac:AwardingCriterion>
					<cbc:CalculationExpression languageID="FRA">Le calcul du score prix-qualité est basé sur …</cbc:CalculationExpression>
					<cac:SubordinateAwardingCriterion>
						<cbc:AwardingCriterionTypeCode listName="award-criterion-type">price</cbc:AwardingCriterionTypeCode>
						<cbc:Description languageID="FRA">Le prix contribue for 40 % …</cbc:Description>
					</cac:SubordinateAwardingCriterion>
				</cac:AwardingCriterion>
			</cac:AwardingTerms>
			<cac:AppealTerms>
				<cac:PresentationPeriod>
					<cbc:Description languageID="FRA">Un appel peut...</cbc:Description>
				</cac:PresentationPeriod>
				<cac:AppealReceiverParty>
					<cac:PartyIdentification>
						<cbc:ID schemeName="organization">ORG-0002</cbc:ID>
					</cac:PartyIdentification>
				</cac:AppealReceiverParty>
			</cac:AppealTerms>
		</cac:TenderingTerms>
		<cac:TenderingProcess>
			<cbc:GovernmentAgreementConstraintIndicator>true</cbc:GovernmentAgreementConstraintIndicator>
			<cac:AuctionTerms>
				<cbc:AuctionConstraintIndicator>true</cbc:AuctionConstraintIndicator>
			</cac:AuctionTerms>
			<cac:ContractingSystem>
				<cbc:ContractingSystemTypeCode listName="framework-agreement">none</cbc:ContractingSystemTypeCode>
			</cac:ContractingSystem>
			<cac:ContractingSystem>
				<cbc:ContractingSystemTypeCode listName="dps-usage">none</cbc:ContractingSystemTypeCode>
			</cac:ContractingSystem>
		</cac:TenderingProcess>
		<cac:ProcurementProject>
			<cbc:ID schemeName="InternalID">1</cbc:ID>
			<cbc:Name languageID="FRA">Agence centre</cbc:Name>
			<cbc:Description languageID="FRA">Service d'entretien de remise en état et de nettoyage des espaces verts.</cbc:Description>
			<cbc:ProcurementTypeCode listName="contract-nature">services</cbc:ProcurementTypeCode>
			<cac:MainCommodityClassification>
				<cbc:ItemClassificationCode listName="cpv">77310000</cbc:ItemClassificationCode>
			</cac:MainCommodityClassification>
			<!--<cac:RealizedLocation>
				<cac:Address>
					<cbc:CountrySubentityCode listName="nuts">FRD22</cbc:CountrySubentityCode>
				</cac:Address>
			</cac:RealizedLocation>
		-->
		</cac:ProcurementProject>
	</cac:ProcurementProjectLot>
	<cac:TenderResult>
		<cbc:AwardDate>2000-01-01Z</cbc:AwardDate>
	</cac:TenderResult>
</ContractAwardNotice>"""

        # Encoding the XML string as bytes
        self.ted_xml = self.ted_xml.encode('utf-8')

        self.expected_ocds_json = {
            "id": "65667997-031a-4198-bd25-7225449ef479",
            "initiationType": "tender",
            "ocid": "blah",
            "date": "2019-10-23T00:00:00+01:00",
            "tag": [
                "award",
                "contract"
            ],
            "language": "FR",
            "parties": [
                {
                "id": "ORG-0004",
                "name": "Espaces Verts Lemire",
                "roles": [
                    "tenderer",
                    "supplier"
                ],
                "address": {
                    "locality": "Le Grand-Quevilly",
                    "postalCode": "ABC123",
                    "region": "FRD22",
                    "country": "FR"
                },
                "details": {
                    "listedOnRegulatedMarket": False,
                    "scale": "micro"
                },
                "beneficialOwners": [
                    {
                    "id": "UBO-0001",
                    "nationality": "FR"
                    }
                ],
                "identifier": {
                    "id": "326 912 557"
                },
                "contactPoint": {
                    "telephone": "+33 2 35 67 82 82",
                    "email": "contact@example.com"
                }
                },
                {
                "id": "ORG-0001",
                "name": "Rouen Habitat",
                "roles": [
                    "buyer"
                ],
                "details": {
                    "classifications": [
                    {
                        "id": "pub-undert-la",
                        "description": "Public undertaking, controlled by a local authority",
                        "scheme": "TED_CA_TYPE"
                    },
                    {
                        "description": "hc-am",
                        "scheme": "COFOG",
                        "id": "06"
                    }
                    ]
                },
                "address": {
                    "locality": "Rouen Cedex 1",
                    "postalCode": "ABC123",
                    "region": "FRD22",
                    "country": "FR"
                },
                "identifier": {
                    "id": "123 456 789"
                },
                "contactPoint": {
                    "telephone": "+33 235156161",
                    "email": "contact@rouenhabitat.fr"
                }
                },
                {
                "id": "ORG-0002",
                "name": "Tribunal administratif de Rouen",
                "address": {
                    "locality": "Rouen",
                    "postalCode": "ABC123",
                    "region": "FRD22",
                    "country": "FR"
                },
                "identifier": {
                    "id": "123 456 789"
                },
                "contactPoint": {
                    "telephone": "+33 232081270",
                    "email": "greffe.ta-rouen@juradm.fr"
                },
                "roles": [
                    "reviewBody"
                ]
                },
                {
                "id": "ORG-EU",
                "name": "European Union",
                "roles": [
                    "funder"
                ]
                }
            ],
            "bids": {
                "details": [
                {
                    "id": "TEN-0001",
                    "rank": 1,
                    "hasRank": True,
                    "value": {
                    "amount": 95414,
                    "currency": "EUR"
                    },
                    "hasSubcontracting": False,
                    "tenderers": [
                    {
                        "id": "ORG-0004"
                    }
                    ],
                    "relatedLots": [
                    "LOT-0000"
                    ]
                }
                ],
                "statistics": [
                {
                    "id": "1",
                    "measure": "highestValidBidValue",
                    "value": {
                    "amount": 95414,
                    "currency": "EUR"
                    },
                    "relatedLots": [
                    "LOT-0000"
                    ]
                },
                {
                    "id": "2",
                    "measure": "lowestValidBidValue",
                    "value": {
                    "amount": 59299.64,
                    "currency": "EUR"
                    },
                    "relatedLots": [
                    "LOT-0000"
                    ]
                },
                {
                    "id": "3",
                    "measure": "bids",
                    "value": 3,
                    "relatedLots": [
                    "LOT-0000"
                    ]
                }
                ]
            },
            "tender": {
                "id": "022d0ef9-6338-42d9-afa4-a87709128061",
                "title": "Service d'entretien de remise en état et de nettoyage des espaces verts",
                "description": "Service d'entretien de remise en état et de nettoyage des espaces verts.",
                "mainProcurementCategory": "services",
                "items": [
                {
                    "id": 1,
                    "classifications":[
                    {
                        "id": "77310000",
                        "scheme": "CPV"
                    }
                    ]        
                }
                ],
                "legalBasis": {
                "id": "32014L0024",
                "scheme": "CELEX"
                },
                "status": "complete",
                "procurementMethod": "open",
                "lots": [
                {
                    "id": "LOT-0000",
                    "title": "Agence centre",
                    "description": "Service d'entretien de remise en état et de nettoyage des espaces verts.",
                    "awardCriteria": {
                    "weightingDescription": "Le calcul du score prix-qualité est basé sur …",
                    "criteria": [
                        {
                        "type": "price",
                        "description": "Le prix contribue for 40 % …"
                        }
                    ]
                    },
                    "mainProcurementCategory": "services",
                    "items": [
                    {
                        "id": "2",
                        "classifications": [
                        {
                            "scheme": "CPV",
                            "id": "77310000"
                        }
                        ]
                    }
                    ],
                    "reviewDetails": "Un appel peut...",
                    "coveredBy": [
                    "GPA"
                    ],
                    "techniques": {
                    "hasElectronicAuction": True
                    },
                    "identifiers": {
                    "id": "1",
                    "scheme": "internal"
                    }
                }
                ]
            },
            "awards": [
                {
                "id": "RES-0001",
                "status": "active",
                "statusDetails": "At least one winner was chosen.",
                "buyers": [
                    {
                    "id": "ORG-0001"
                    }
                ],
                "suppliers": [
                    {
                    "id": "ORG-0004"
                    }
                ],
                "value": {
                    "amount": 95414,
                    "currency": "EUR"
                },
                "relatedLots": [
                    "LOT-0000"
                ],
                "relatedBids": [
                    "TEN-0001"
                ]
                }
            ],
            "contracts": [
                {
                "id": "CON-0001",
                "awardID": "RES-0001",
                "dateSigned": "2019-09-03T00:00:00+02:00",
                "identifiers": [
                    {
                    "id": "SCN DEF:2020-12",
                    "scheme": "FR-SCN DEF"
                    }
                ],
                "relatedBids": [
                    "TEN-0001"
                ]
                }
            ]
        }

    def test_conversion(self):
        # Create a file-like object from the bytes XML content
        xml_file = io.BytesIO(self.ted_xml)

        # Perform conversion
        result = convert_ted_to_ocds(xml_file)
        ocds_json = json.loads(result)

        try:
            self.maxDiff = None  # Disable max diff limits for more comprehensive output

            # Checking top level attributes consistency with thorough nested checks
            self.assertEqual(ocds_json['releases'][0]['id'], self.expected_ocds_json['id'])
            self.assertEqual(ocds_json['releases'][0]['initiationType'], self.expected_ocds_json['initiationType'])
            self.assertEqual(ocds_json["releases"][0]["date"], self.expected_ocds_json["date"])
            self.assertEqual(ocds_json['releases'][0]['tag'], self.expected_ocds_json['tag'])
            self.assertEqual(ocds_json['releases'][0]['language'], self.expected_ocds_json['language'])
            self.assertEqual(ocds_json['releases'][0]['parties'], self.expected_ocds_json['parties'])
            #self.assertEqual(ocds_json['releases'][0]['bids'], self.expected_ocds_json['bids'])
            #self.assertEqual(ocds_json['releases'][0]['tender'], self.expected_ocds_json['tender'])
            #self.assertEqual(ocds_json['releases'][0]['awards'], self.expected_ocds_json['awards'])
            #self.assertEqual(ocds_json['releases'][0]['contracts'], self.expected_ocds_json['contracts'])

            # Compare parties and print differences if there are any
            actual_parties = ocds_json['releases'][0]['parties']
            expected_parties = self.expected_ocds_json['releases'][0]['parties']

            for i, (actual, expected) in enumerate(zip(actual_parties, expected_parties)):
                if actual != expected:
                    print(f"Difference at index {i}:\nActual: {json.dumps(actual, indent=2, ensure_ascii=False)}\nExpected: {json.dumps(expected, indent=2, ensure_ascii=False)}")

            self.assertEqual(actual_parties, expected_parties)

        except AssertionError as e:
            print(f"Differences in test output: {e}")
            print("Detailed diff:")
            print("Expected Output:", json.dumps(self.expected_ocds_json, indent=2, ensure_ascii=False))
            print("Actual Output:", json.dumps(ocds_json, indent=2, ensure_ascii=False))
            raise

if __name__ == "__main__":
    unittest.main()