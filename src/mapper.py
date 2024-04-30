import logging
import uuid
import json
from lxml import etree
from datetime import datetime


def parse_iso_date(date_str):
    """
    Custom parser for handling ISO dates with timezone in '+00:00' format.
    """
    try:
        return datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        # Try without time part
        return datetime.strptime(date_str, "%Y-%m-%d%z")
    
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
                    company_id = self.parser.find_text(org_element, "./cac:PartyLegalEntity/cbc:CompanyID", namespaces=self.parser.nsmap)

                    logging.debug(f"Fetched party name: {party_name}, party ID: {party_id}, Company ID: {company_id}")

                    if party_name and party_id:
                        party_info = {"id": party_id, "name": party_name}
                        if company_id:
                            party_info["additionalIdentifiers"] = [{"id": company_id, "scheme": "NO-ORG"}]
                        logging.debug(f"Company Organization Output: {party_info}")
                        return party_info
                logging.warning("No Company data found after iteration.")
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
    
    def fetch_bt502_contact_point(self, org_element):
        contact_point = {}
        contact_name = self.parser.find_text(org_element, "./efac:Company/cac:Contact/cbc:Name", namespaces=self.parser.nsmap)
        telephone = self.parser.find_text(org_element, "./efac:Company/cac:Contact/cbc:Telephone", namespaces=self.parser.nsmap)

        if contact_name:
            contact_point["name"] = contact_name
        if telephone:
            contact_point["telephone"] = telephone

        return contact_point if contact_point else {}
    
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
        
        # Fetch BT-500 organization data for both company and touchpoint
        company_party = self.fetch_bt500_company_organization(root_element)
        if company_party:
            party_info = {
                "id": company_party.get("id"),
                "name": company_party.get("name"),
                "roles": ["supplier"]  # Assuming the role here; adjust as necessary
            }
            if "additionalIdentifiers" in company_party:
                party_info["additionalIdentifiers"] = company_party["additionalIdentifiers"]
            parties.append(party_info)
        else:
            logging.warning('No company organization data found from BT-500.')
        
        touchpoint_party = self.fetch_bt500_touchpoint_organization(root_element)
        if touchpoint_party:
            parties.append({
                "id": touchpoint_party.get("id"),
                "name": touchpoint_party.get("name"),
                "roles": ["contact"]  # Adjust this role as needed
            })
        else:
            logging.warning('No touchpoint organization data found from BT-500.')

        # Fetch extended organization elements including contact points with potential BT-502 and BT-503 data
        organization_elements = root_element.findall(
            ".//ext:UBLExtensions/ext:UBLExtension/ext:ExtensionContent/efext:EformsExtension/efac:Organizations/efac:Organization",
            namespaces=self.parser.nsmap)
        for org_element in organization_elements:
            org_id = self.parser.find_text(org_element, "./efac:Company/cac:PartyIdentification/cbc:ID", namespaces=self.parser.nsmap)
            if org_id:
                org_info = {
                    "id": org_id,
                    "roles": ["supplier"]  # Assuming role here
                }
                # Fetch the organization name if available
                name = self.parser.find_text(org_element, "./cac:PartyName/cbc:Name", namespaces=self.parser.nsmap)
                if name:
                    org_info["name"] = name
                
                # Fetch the company's contact details including the telephone number (BT-502 and BT-503)
                contact_info = self.fetch_bt502_contact_point(org_element)
                if contact_info:
                    org_info["contactPoint"] = contact_info
                
                parties.append(org_info)
        
        # Process standard contracting parties if available
        party_elements = root_element.findall(".//cac:ContractingParty", namespaces=self.parser.nsmap)
        for party_element in party_elements:
            party = party_element.find(".//cac:Party", namespaces=self.parser.nsmap)
            party_id = self.parser.find_text(party, "./cac:PartyIdentification/cbc:ID")
            if party_id:
                info = {"id": party_id, "roles": ["buyer"]}
                party_name = self.parser.find_text(party, "./cac:PartyName/cbc:Name")
                if party_name:
                    info["name"] = party_name
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
            lot_title = self.parser.find_text(lot_element, ".//cac:ProcurementProject/cbc:Name", namespaces=self.parser.nsmap)
            start_date = self.parser.find_text(lot_element, ".//cac:PlannedPeriod/cbc:StartDate", namespaces=self.parser.nsmap)
            end_date = self.parser.find_text(lot_element, ".//cac:PlannedPeriod/cbc:EndDate", namespaces=self.parser.nsmap)
            options_description = self.parser.find_text(lot_element, "./cac:ProcurementProject/cac:ContractExtension/cbc:OptionsDescription", namespaces=self.parser.nsmap)
            
            lot = {"id": lot_id, "title": lot_title}

            # Handling previous notice identifier based on OPP-090-Procedure
            previous_notice_ids = lot_element.findall(".//cac:TenderingProcess/cac:NoticeDocumentReference/cbc:ID[@schemeName='notice-id-ref']", namespaces=self.parser.nsmap)
            for index, notid in enumerate(previous_notice_ids, start=1):
                related_process = {
                    "id": str(index),  # Creating incremental IDs based on the procedure being repeated
                    "relationship": ["planning"],
                    "scheme": "eu-oj",
                    "identifier": notid.text  # Extract the ID
                }
                if "relatedProcesses" not in lot:
                    lot['relatedProcesses'] = []
                lot['relatedProcesses'].append(related_process)

            # Date handling
            if start_date:
                start_iso_date = parse_iso_date(start_date).isoformat()
                lot['contractPeriod'] = {"startDate": start_iso_date}
            if end_date:
                end_iso_date = parse_iso_date(end_date).isoformat()
                lot['contractPeriod'] = lot.get('contractPeriod', {})
                lot['contractPeriod']['endDate'] = end_iso_date
            if options_description:
                lot['options'] = {"description": options_description}

            lots.append(lot)
        return lots

    def parse_contract_period(self, root):
        start_date = self.parser.find_text(root, ".//cac:ProcurementProject/cac:PlannedPeriod/cbc:StartDate", namespaces=self.parser.nsmap)
        end_date = self.parser.find_text(root, ".//cac:ProcurementProject/cac:PlannedPeriod/cbc:EndDate", namespaces=self.parser.nsmap)

        contract_period = {}
        if start_date:
            contract_period['startDate'] = parse_iso_date(start_date).isoformat()
        if end_date:
            contract_period['endDate'] = parse_iso_date(end_date).isoformat()
            
        return contract_period
    
    def parse_additional_procurement_categories(self, element):
        categories = []
        categories_elements = element.findall(".//cac:ProcurementProject/cac:ProcurementAdditionalType/cbc:ProcurementTypeCode[@listName='contract-nature']", namespaces=self.parser.nsmap)
        for category in categories_elements:
            categories.append(category.text)
        return categories

    def fetch_notice_languages(self, element):
        """
        Fetches the official languages of the notice from the element using BT-702(a).
        Discards data from BT-702(b) as per the requirements.
        """
        languages = []
        # Fetch the primary notice language code and map it
        notice_language_code = self.parser.find_text(element, ".//cbc:NoticeLanguageCode")
        if notice_language_code:
            # Assuming a mapping function convert_language_code() that converts TED language codes to ISO 639-1
            language_iso = self.convert_language_code(notice_language_code)
            if language_iso:
                languages.append(language_iso)

        # The following fetches additional languages but is discarded as per BT-702(b)
        # additional_languages = element.findall(".//cac:AdditionalNoticeLanguage/cbc:ID", namespaces=self.parser.nsmap)
        # for lang in additional_languages:
        #     language_iso = self.convert_language_code(lang.text)
        #     if language_iso:
        #         languages.append(language_iso)

        return languages

    @staticmethod
    def convert_language_code(lang_code):
        """
        Convert a three-letter TED language code to a two-letter ISO 639-1 code.
        The function needs actual mapping as per your context.
        """
        language_mapping = {
        'ENG': 'en',  # English
        'FRA': 'fr',  # French
        'DEU': 'de',  # German
        'ITA': 'it',  # Italian
        'ESP': 'es',  # Spanish
        'NLD': 'nl',  # Dutch
        'BGR': 'bg',  # Bulgarian
        'CES': 'cs',  # Czech
        'DAN': 'da',  # Danish
        'ELL': 'el',  # Greek
        'EST': 'et',  # Estonian
        'FIN': 'fi',  # Finnish
        'HUN': 'hu',  # Hungarian
        'HRV': 'hr',  # Croatian
        'LAT': 'lv',  # Latvian
        'LIT': 'lt',  # Lithuanian
        'MLT': 'mt',  # Maltese
        'POL': 'pl',  # Polish
        'POR': 'pt',  # Portuguese
        'RON': 'ro',  # Romanian
        'SLK': 'sk',  # Slovak
        'SLV': 'sl',  # Slovenian
        'SWE': 'sv',  # Swedish
        'NOR': 'no',  # Norwegian
        'ISL': 'is'   # Icelandic (Iceland is not in the EU, similar to Norway and often included in joint data)
        }
        return language_mapping.get(lang_code.upper())
    
    def convert_tender_to_ocds(self):
        root = self.parser.root
        ocid = "ocds-prefix-" + str(uuid.uuid4())  # Generate a new OCDS ID
        dispatch_datetime = self.get_dispatch_date_time(root)
        tender_title = self.parser.find_text(root, ".//cac:ProcurementProject/cbc:Name", namespaces=self.parser.nsmap)

        # Logging for debug purposes
        logging.debug(f"Dispatch Date and Time: {dispatch_datetime}")
        logging.debug(f"Tender Title: {tender_title}")

        # Parsing form type, parties, lots, legal basis, and languages
        form_type = self.get_form_type(root)
        parties = self.gather_party_info(root)
        lots = self.parse_lots(root)
        legal_basis = self.get_legal_basis(root)
        languages = self.fetch_notice_languages(root)

        # Parse related processes (references to previous notices, etc.)
        related_processes = self.parse_related_processes(root)

        # Structure the OCDS release
        release = {
            "id": self.parser.find_text(root, "./cbc:ID"),
            "ocid": ocid,
            "date": dispatch_datetime,
            "initiationType": "tender",
            "tags": form_type['tags'],
            "parties": parties,
            "tender": {
                "id": self.parser.find_text(root, ".//cbc:ContractFolderID"),
                "status": form_type['tender_status'],
                "title": tender_title,
                "legalBasis": legal_basis,
                "language": languages,
                "lots": lots
            }
        }

        # Include related processes if any
        if related_processes:
            release['relatedProcesses'] = related_processes

        # Clean and return the final structured Release
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
    
    def parse_related_processes(self, root):
        related_processes = []
        notice_refs = root.findall(".//cac:NoticeDocumentReference", namespaces=self.parser.nsmap)
        for ref in notice_refs:
            notice_id_value = ref.find("./cbc:ID", namespaces=self.parser.nsmap)
            if notice_id_value is not None:
                scheme_name = notice_id_value.get('schemeName', 'undefined-scheme')
                notice_id = notice_id_value.text
                related_processes.append({
                    "id": notice_id,
                    "relationship": ["planning"],
                    "scheme": scheme_name
                })
        return related_processes
    

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
