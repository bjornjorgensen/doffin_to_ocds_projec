import logging
import uuid
import json
from lxml import etree


class XMLParser:
    def __init__(self, xml_file):
        self.tree = etree.parse(xml_file)
        self.root = self.tree.getroot()
        self.nsmap = {
                'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
                'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
                'efac': 'http://data.europa.eu/p27/eforms-ubl-extension-aggregate-components/1',
                'efbc': 'http://data.europa.eu/p27/eforms-ubl-extension-basic-components/1',
                'efext': 'http://data.europa.eu/p27/eforms-ubl-extensions/1',
                'ext': 'urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2'
        }
        logging.info(f'XMLParser initialized with file: {xml_file}')

    def find_text(self, element, xpath, namespaces=None):
        if xpath.startswith("//"):
            xpath = ".//" + xpath[2:]
        node = element.find(xpath, namespaces=namespaces if namespaces else self.nsmap)
        return node.text if node is not None else None

    def find_attribute(self, element, xpath, attribute, default=None):
        if xpath.startswith("//"):
            xpath = ".\\" + xpath
        node = element.find(xpath, namespaces=self.nsmap)
        return node.get(attribute) if node is not None else default

class TEDtoOCDSConverter:
    def __init__(self, parser):
        self.parser = parser
        self.form_type_mapping = {
            'planning': {'tags': ['tender'], 'tender_status': 'planned'},
            'competition': {'tags': ['tender'], 'tender_status': 'active'},
            'change': {'tags': ['tenderUpdate'], 'tender_status': None},
            'result': {'tags': ['award', 'contract'], 'tender_status': 'complete'},
            'dir-awa-pre': {'tags': ['award', 'contract'], 'tender_status': 'complete'},
            'cont-modif': {'tags': ['awardUpdate', 'contractUpdate'], 'tender_status': None}
        }
        logging.info('TEDtoOCDSConverter initialized with mapping.')

    def fetch_bt500_company_organization(self, root_element):
        try:
            organizations_element = root_element.find(".//ext:UBLExtensions/ext:UBLExtension/ext:ExtensionContent/efext:EformsExtension/efac:Organizations", namespaces=self.parser.nsmap)
            if organizations_element is not None:
                for org_element in organizations_element.findall("./efac:Organization/efac:Company", namespaces=self.parser.nsmap):
                    party_name = self.parser.find_text(org_element, "./cac:PartyName/cbc:Name", namespaces=self.parser.nsmap)
                    party_id = self.parser.find_text(org_element, "./cac:PartyIdentification/cbc:ID", namespaces=self.parser.nsmap)
                    if party_name and party_id:
                        return {"id": party_id, "name": party_name}
        except Exception as e:
            logging.error(f"Failed while fetching company organization: {str(e)}")
        return {}

    def fetch_bt500_touchpoint_organization(self, element):
        xpath = ".//efac:Organizations/efac:Organization/efac:TouchPoint/cac:PartyName/cbc:Name"
        name = self.parser.find_text(element, xpath, namespaces=self.parser.nsmap)
        ident_xpath = ".//efac:Organizations/efac:Organization/efac:TouchPoint/cac:PartyIdentification/cbc:ID"
        identifier = self.parser.find_text(element, ident_xpath, namespaces=self.parser.nsmap)
        company_id_xpath = ".//efac:Organizations/efac:Organization/efac:Company/cac:PartyLegalEntity/cbc:CompanyID"
        company_id = self.parser.find_text(element, company_id_xpath, namespaces=self.parser.nsmap)
        return {"id": identifier, "name": name, "identifier": {"id": company_id, "scheme": "internal"}} if name else {}
    
    def get_dispatch_date_time(self, root):
        issue_date = self.parser.find_text(root, ".//cbc:IssueDate")
        issue_time = self.parser.find_text(root, ".//cbc:IssueTime")
        if issue_date and issue_time:
            return f"{issue_date}T{issue_time}"
        return None

    def get_legal_basis(self, element):
        legal_basis = {}
        all_basis = element.findall(".//cac:TenderingTerms/cac:ProcurementLegislationDocumentReference",
                                     namespaces=self.parser.nsmap)
        for ref in all_basis:
            id_text = self.parser.find_text(ref, "./cbc:ID")
            if id_text == "LocalLegalBasis":
                legal_basis['id'] = 'LocalLegalBasis'
                description = self.parser.find_text(ref, "./cbc:DocumentDescription")
                if description:
                    legal_basis['description'] = description
                break
        celex_code = self.parser.find_text(element, ".//cbc:RegulatoryDomain")
        if celex_code:
            legal_basis = {'scheme': 'CELEX', 'id': celex_code}
        return legal_basis

    def gather_party_info(self, root_element):
        parties = []

        # Fetch parties using specialized functions for BT-500 organization company and touchpoint
        company_party = self.fetch_bt500_company_organization(root_element)
        if company_party:
            parties.append({
                "id": company_party.get("id"),
                "name": company_party.get("name"),
                "roles": ["supplier"]  # Assuming the role here, adjust as needed
            })
        else:
            logging.warning('No company organization data found.')
        
        touchpoint_party = self.fetch_bt500_touchpoint_organization(root_element)
        if touchpoint_party:
            parties.append({
                "id": touchpoint_party.get("id"),
                "name": touchpoint_party.get("name"),
                "roles": ["supplier"]  # Assuming the role here, adjust as needed
            })
        else:
            logging.warning('No touchpoint organization data found.')
        
        # Fetch standard contracting parties from the element provided
        party_elements = root_element.findall(".//cac:ContractingParty", namespaces=self.parser.nsmap)
        for party_element in party_elements:
            party = party_element.find(".//cac:Party", namespaces=self.parser.nsmap)
            party_id = self.parser.find_text(party, "./cac:PartyIdentification/cbc:ID")
            
            # Attempt fetching the activity code
            activity_code_element = party_element.find(".//cac:ContractingActivity/cbc:ActivityTypeCode[@listName='authority-activity']", namespaces=self.parser.nsmap)
            activity_code = activity_code_element.text if activity_code_element is not None else None

            logging.debug(f'Extracted activity code for party ID {party_id}: {activity_code}')

            if party_id:
                info = {"id": party_id, "roles": ["buyer"]}

                # Find the name of the party
                party_name = self.parser.find_text(party, "./cac:PartyName/cbc:Name")
                
                if party_name:
                    info["name"] = party_name
                
                # Set up additional details if an activity code was found
                if activity_code:
                    activity_description = self.get_activity_description(activity_code)
                    scheme, code, description = self.map_activity_code(activity_code, activity_description)
                    info["details"] = {
                        "classifications": [
                            {
                                "scheme": scheme,
                                "id": code,
                                "description": description
                            }
                        ]
                    }
                    logging.debug(f'Party details for ID {party_id}: {info["details"]}')
                else:
                    info["details"] = {}
                    logging.warning(f'No activity code found for party ID {party_id}')
                
                parties.append(info)
            else:
                logging.warning('Party element found without an ID!')

        return parties

    def get_activity_description(self, activity_code):
        activity_descriptions = {
            "airport": "Airport-related activities",
            "defence": "Defence",
            "economic": "Economic affairs",
            "education": "Education",
            "electricity": "Electricity-related activities",
            "environment": "Environmental protection",
            "coal": "Exploration or extraction of coal or other solid fuels",
            "gas-oil": "Extraction of gas or oil",
            "public-services": "General public services",
            "health": "Health",
            "housing": "Housing and community amenities",
            "port": "Port-related activities",
            "postal": "Postal services",
            "gas-heat": "Production, transport or distribution of gas or heat",
            "public-order": "Public order and safety",
            "railway": "Railway services",
            "recreation": "Recreation, culture and religion",
            "social": "Social protection",
            "urban-transport": "Urban railway, tramway, trolleybus or bus services",
            "water": "Water-related activities",
            "gen-pub": "General public services"
        }
        return activity_descriptions.get(activity_code, "")

    def map_activity_code(self, activity_code, activity_description):
        if "COFOG" in activity_description:
            scheme = "COFOG"
            cofog_mapping = {
                "gas-oil": "04.2.2",  # Fuel and energy
                "coal": "04.2.1",  # Mining, manufacturing and construction
                "electricity": "04.2.2",  # Fuel and energy
                "gas-heat": "04.2.2",  # Fuel and energy
                "port": "04.5.2",  # Transport
                "railway": "04.5.2",  # Transport
                "urban-transport": "04.5.2",  # Transport
                "airport": "04.5.2",  # Transport
                "water": "06.3.0",  # Water supply
                "environment": "05.0.0",  # Environmental protection
                "housing": "06.1.0",  # Housing development
                "health": "07.0.0",  # Health
                "recreation": "08.0.0",  # Recreation, culture and religion
                "education": "09.0.0",  # Education
                "social": "10.0.0",  # Social protection
                "public-services": "01.0.0",  # General public services
                "public-order": "03.0.0",  # Public order and safety
                "defence": "02.0.0",  # Defence
                "economic": "04.0.0",  # Economic affairs
                "postal": "04.7.0"  # Other industries
            }
            cofog_code = cofog_mapping.get(activity_code, "")
            un_mapping = {
                "04.2.2": "12",  # Crude petroleum and natural gas
                "04.2.1": "11",  # Coal and peat
                "04.5.2": "64",  # Passenger transport services
                "06.3.0": "18",  # Natural water
                "05.0.0": "94",  # Sewage and waste collection, treatment and disposal and other environmental protection services
                "06.1.0": "72",  # Real estate services
                "07.0.0": "93",  # Human health and social care services
                "08.0.0": "96",  # Recreational, cultural and sporting services
                "09.0.0": "92",  # Education services
                "10.0.0": "93",  # Human health and social care services
                "01.0.0": "91",  # Public administration and other services provided to the community as a whole; compulsory social security services
                "03.0.0": "91",  # Public administration and other services provided to the community as a whole; compulsory social security services
                "02.0.0": "91",  # Public administration and other services provided to the community as a whole; compulsory social security services
                "04.0.0": "83",  # Professional, technical and business services (except research, development, legal and accounting services)
                "04.7.0": "68"  # Postal and courier services
            }
            code = un_mapping.get(cofog_code, "")
            description = activity_description
        else:
            scheme = "eu-main-activity"
            description = self.get_activity_description(activity_code)
            if activity_code == "gen-pub":
                code = "01.0.0"
            else:
                code = activity_code
        return scheme, code, description

    def get_form_type(self, element):
        form_type_code = self.parser.find_attribute(element, ".//cbc:NoticeTypeCode", "listName")
        return self.form_type_mapping.get(form_type_code, {'tags': [], 'tender_status': 'planned'})

    def parse_lots(self, element):
        lots = []
        lot_elements = element.findall(".//cac:ProcurementProjectLot", namespaces=self.parser.nsmap)
        for lot_element in lot_elements:
            lot_id = self.parser.find_text(lot_element, "./cbc:ID")
            lot_title = self.parser.find_text(lot_element,
                                              ".//cac:ProcurementProject/cbc:Name",
                                              namespaces=self.parser.nsmap)
            if lot_id:
                lot = {"id": lot_id, "title": lot_title}
                lots.append(lot)
        return lots

    def convert_tender_to_ocds(self):
        root = self.parser.root
        form_type = self.get_form_type(root)
        dispatch_datetime = self.get_dispatch_date_time(root)
        tender_title = self.parser.find_text(root, ".//cac:ProcurementProject/cbc:Name",
                                             namespaces=self.parser.nsmap) 
        release = {
            "id": self.parser.find_text(root, "./cbc:ID"),
            "initiationType": "tender",
            "ocid": "ocds-prefix-" + str(uuid.uuid4()),
            "date": dispatch_datetime,
            "parties": self.gather_party_info(root),
            "tender": {
                "id": self.parser.find_text(root, ".//cbc:ContractFolderID"),
                "legalBasis": self.get_legal_basis(root),
                "status": form_type['tender_status'],
                "title": tender_title,
                "lots": self.parse_lots(root)
            },
            "tags": form_type['tags']
        }
        cleaned_release = self.clean_release_structure(release)
        logging.info('Conversion to OCDS format completed.')
        return cleaned_release

    def clean_release_structure(self, data):
        if isinstance(data, dict):
            cleaned = {k: self.clean_release_structure(v) for k, v in data.items() if v is not None}
            return {k: v for k, v in cleaned.items() if v}
        elif isinstance(data, list):
            return [self.clean_release_structure(v) for v in data if v is not None]
        return data

def convert_ted_to_ocds(xml_file):
    logging.basicConfig(level=logging.DEBUG)
    logging.info(f'Starting conversion for file: {xml_file}')
    parser = XMLParser(xml_file)
    converter = TEDtoOCDSConverter(parser)
    release_info = converter.convert_tender_to_ocds()
    releases = [release_info]
    result = json.dumps({"releases": releases}, indent=2, ensure_ascii=False)
    logging.info('Conversion complete, output prepared.')
    return result

# Example usage
xml_file = "2022-319091.xml"
ocds_json = convert_ted_to_ocds(xml_file)
print(ocds_json)
