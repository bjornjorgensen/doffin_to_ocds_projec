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
            'ext': 'urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2',
            'efext': 'urn:oasis:names:specification:eforms:extensions:schema:xsd:CommonExtensionComponents-1',
            'efac': 'urn:oasis:names:specification:eforms:extensions:schema:xsd:CommonAggregateComponents-1',
            'efbc': 'urn:oasis:names:specification:eforms:extensions:schema:xsd:CommonBasicComponents-1'
        }
        logging.info(f'XMLParser initialized with file: {xml_file}')

    def find_text(self, element, xpath):
        # Using .// if xpath begins with // to prevent absolute path error
        if xpath.startswith("//"):
            xpath = ".\\" + xpath
        node = element.find(xpath, namespaces=self.nsmap)
        result = node.text if node is not None else None
        logging.debug(f'Finding text, XPath: {xpath}, Result: {result}')
        return result

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

    def gather_party_info(self, element):
        parties = []
        party_elements = element.findall(".//cac:ContractingParty/cac:Party", namespaces=self.parser.nsmap)
        for party_element in party_elements:
            party_id = self.parser.find_text(party_element, "./cac:PartyIdentification/cbc:ID")
            if party_id:
                parties.append({"id": party_id, "roles": ["buyer"]})
        return parties

    def get_form_type(self, element):
        form_type_code = self.parser.find_attribute(element, ".//cbc:NoticeTypeCode", "listName")
        return self.form_type_mapping.get(form_type_code, {'tags': [], 'tender_status': 'planned'})

    def parse_lots(self, element):
        lots = []
        lot_elements = element.findall(".//cac:ProcurementProjectLot", namespaces=self.parser.nsmap)
        for lot_element in lot_elements:
            lot_id = self.parser.find_text(lot_element, "./cbc:ID")
            if lot_id:
                lot = {"id": lot_id}  # Placeholder for extended information
                lots.append(lot)
        return lots

    def convert_tender_to_ocds(self):
        root = self.parser.root
        form_type = self.get_form_type(root)
        dispatch_datetime = self.get_dispatch_date_time(root)
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
    logging.basicConfig(level=logging.INFO)
    logging.info(f'Starting conversion for file: {xml_file}')
    parser = XMLParser(xml_file)
    converter = TEDtoOCDSConverter(parser)
    release_info = converter.convert_tender_to_ocds()
    releases = [release_info]
    result = json.dumps({"releases": releases}, indent=2)
    logging.info('Conversion complete, output prepared.')
    return result

# Example usage
xml_file = "2023-653367.xml"
ocds_json = convert_ted_to_ocds(xml_file)
print(ocds_json)
