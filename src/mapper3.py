from lxml import etree
from collections import defaultdict
import uuid
from datetime import datetime

FORM_TYPE_MAPPING = {
    "competition": {"tag": ["tender"], "status": "active"},
    # Add additional mappings as necessary
}


STRATEGIC_PROCUREMENT_MAPPING = {
    "inn-pur": "economic.innovativePurchase"
    # Add any required mappings if necessary
}

PROCUREMENT_PROCEDURE_TYPE_MAPPING = {
    "open": {"procurementMethod": "open", "procurementMethodDetails": "Open procedure"},
    "restr": {"procurementMethod": "selective", "procurementMethodDetails": "Restricted procedure"},
    "comp": {"procurementMethod": "competitive", "procurementMethodDetails": "Competitive procedure with negotiation"},
    "neg-with-call": {"procurementMethod": "negotiated", "procurementMethodDetails": "Negotiated procedure with prior call"},
    "neg-without-call": {"procurementMethod": "negotiated", "procurementMethodDetails": "Negotiated procedure without prior call"},
    # Add more mappings as needed
}

BUYER_LEGAL_TYPE_DESCRIPTIONS = {
    "body-pl": "Body governed by public law",
    "central-gov": "Central government authority",
    "public-undertaking": "Public undertaking"
}

def lookup_form_type(list_name_value):
    return FORM_TYPE_MAPPING.get(list_name_value, {"tag": [], "status": "undefined"})

def get_regulatory_domain(root, ns):
    regulatory_domain = root.find("./cbc:RegulatoryDomain", namespaces=ns)
    if regulatory_domain is not None:
        return {
            "id": regulatory_domain.text,
            "scheme": "CELEX"
        }
    return None

def get_notice_type_code(root, ns, lookup_form_type):
    for notice_type_code in root.findall(".//cbc:NoticeTypeCode", namespaces=ns):
        list_name = notice_type_code.get("listName")
        if list_name:
            form_type_data = lookup_form_type(list_name)
            return {
                "tag": form_type_data["tag"],
                "status": form_type_data["status"]
            }
    return None

def get_contract_folder_id(root, ns):
    contract_folder_id = root.find(".//cbc:ContractFolderID", namespaces=ns)
    if contract_folder_id is not None:
        return contract_folder_id.text
    return None

def get_issue_date_time(root, ns):
    issue_date = root.findtext(".//cbc:IssueDate", namespaces=ns)
    issue_time = root.findtext(".//cbc:IssueTime", namespaces=ns)
    if issue_date and issue_time:
        return f"{issue_date}T{issue_time}"
    return None

def get_legal_basis(root, ns):
    legal_basis_data = {}
    for legislation_ref in root.findall(".//cac:TenderingTerms/cac:ProcurementLegislationDocumentReference", namespaces=ns):
        id_element = legislation_ref.find('cbc:ID', namespaces=ns)
        description_element = legislation_ref.find('cbc:DocumentDescription', namespaces=ns)
        id_text = id_element.text if id_element is not None else None
        description_text = description_element.text if description_element is not None else None

        if id_text == 'LocalLegalBasis' and description_text:
            legal_basis_data["description"] = description_text
        elif id_text:
            legal_basis_data["id"] = id_text
            if description_text:
                legal_basis_data["description"] = description_text
            if id_element.get('schemeName'):
                legal_basis_data["scheme"] = id_element.get('schemeName')

    return legal_basis_data if legal_basis_data else None

def get_lot_strategic_procurement(root, ns):
    lots = []
    for lot in root.findall(".//cac:ProcurementProjectLot", namespaces=ns):
        lot_id_element = lot.find("cbc:ID[@schemeName='Lot']", namespaces=ns)
        if lot_id_element is not None:
            lot_id = lot_id_element.text
            lot_data = {
                "id": lot_id,
                "hasSustainability": False,
                "sustainability": []
            }

            # Handling of Framework Agreement attributes
            framework_agreement = lot.find(".//cac:TenderingProcess/cac:FrameworkAgreement", namespaces=ns)
            if framework_agreement is not None:
                fa_data = {}

                # Justification
                justification_element = framework_agreement.find(".//cbc:Justification", namespaces=ns)
                if justification_element is not None:
                    fa_data['periodRationale'] = justification_element.text

                # Buyer Categories
                buyer_categories_element = framework_agreement.find(".//cac:SubsequentProcessTenderRequirement[cbc:Name='buyer-categories']/cbc:Description", namespaces=ns)
                if buyer_categories_element is not None:
                    fa_data['buyerCategories'] = buyer_categories_element.text

                # Maximum Participants
                max_participants_element = framework_agreement.find(".//cbc:MaximumOperatorQuantity", namespaces=ns)
                if max_participants_element is not None:
                    fa_data['maximumParticipants'] = int(max_participants_element.text)

                if fa_data:
                    lot_data['techniques'] = {'frameworkAgreement': fa_data}

            # Sustainability procurement types
            procurement_project = lot.find("cac:ProcurementProject", namespaces=ns)
            if procurement_project is not None and len(procurement_project) > 0:
                procurement_types = procurement_project.findall("cac:ProcurementAdditionalType/cbc:ProcurementTypeCode[@listName='strategic-procurement']", namespaces=ns)
                for procurement_type in procurement_types:
                    code = procurement_type.text
                    if code != "none":
                        lot_data["hasSustainability"] = True
                        sustainability_goal = STRATEGIC_PROCUREMENT_MAPPING.get(code)
                        if sustainability_goal:
                            sustainability_data = {
                                "goal": sustainability_goal,
                                "strategies": ["awardCriteria", "contractPerformanceConditions", "selectionCriteria", "technicalSpecifications"]
                            }
                            lot_data["sustainability"].append(sustainability_data)

            lots.append(lot_data)
    return lots

def get_cross_border_law(root, ns):
    """
    Extracts and returns the Cross Border Law description if available.
    """
    cross_border_law_element = root.find(".//cac:TenderingTerms/cac:ProcurementLegislationDocumentReference[cbc:ID='CrossBorderLaw']/cbc:DocumentDescription", namespaces=ns)
    if cross_border_law_element is not None:
        return cross_border_law_element.text
    return None

def get_buyer_activity_authority(root, ns):
    contracting_party = root.find(".//cac:ContractingParty", namespaces=ns)
    if contracting_party is not None:
        activity_type_code = contracting_party.find(".//cac:ContractingActivity/cbc:ActivityTypeCode[@listName='BuyerActivityList']", namespaces=ns)
        if activity_type_code is not None:
            code = activity_type_code.text
            return {
                "scheme": "eu-main-activity",
                "id": code,
                "description": code  # Use the code as the description placeholder
            }
    return None

def get_procedure_type(root, ns):
    procedure_code_element = root.find(".//cbc:ProcedureCode[@listName='procurement-procedure-type']", namespaces=ns)
    if procedure_code_element is not None:
        procedure_code = procedure_code_element.text
        procedure_mapping = PROCUREMENT_PROCEDURE_TYPE_MAPPING.get(procedure_code)
        if procedure_mapping:
            return procedure_mapping
    return None

def is_procedure_accelerated(root, ns):
    process_reason_element = root.find(".//cac:TenderingProcess/cac:ProcessJustification/cbc:ProcessReasonCode[@listName='accelerated-procedure']", namespaces=ns)
    if process_reason_element is not None:
        return process_reason_element.text.lower() == "true"
    return False

def get_buyer_details(root, ns):
    contracting_party = root.find(".//cac:ContractingParty", namespaces=ns)
    # Explicit check for both existence and if it is non-empty
    if contracting_party is not None and len(contracting_party):
        buyer_id_element = contracting_party.find(".//cbc:ID[@schemeName='organization']", namespaces=ns)
        buyer_legal_type_element = contracting_party.find(".//cbc:PartyTypeCode[@listName='buyer-legal-type']", namespaces=ns)
        
        if buyer_legal_type_element is not None and buyer_legal_type_element.text:
            legal_type_code = buyer_legal_type_element.text.strip()
            buyer_details = {
                "id": buyer_id_element.text.strip() if buyer_id_element is not None else "Unknown ID",
                "details": {
                    "classifications": [
                        {
                            "scheme": "TED_CA_TYPE",
                            "id": legal_type_code,
                            "description": BUYER_LEGAL_TYPE_DESCRIPTIONS.get(legal_type_code, "Unknown legal type")
                        }
                    ]
                }
            }
            return buyer_details
    return None

def eform_to_ocds(eform_xml, lookup_form_type):
    root = etree.fromstring(eform_xml)
    ns = {
        'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
        'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2'
    }

    ocds_data = {"tender": {}}
    buyer_details = get_buyer_details(root, ns)

    if buyer_details:
        ocds_data["parties"] = [buyer_details]

    # RegulatoryDomain handling for BT-01
    regulatory_domain = get_regulatory_domain(root, ns)
    if regulatory_domain:
        ocds_data["tender"]["legalBasis"] = regulatory_domain

    # Process each NoticeTypeCode element
    notice_type_code_data = get_notice_type_code(root, ns, lookup_form_type)
    if notice_type_code_data:
        ocds_data["tag"] = notice_type_code_data["tag"]
        ocds_data["tender"]["status"] = notice_type_code_data["status"]

    # ContractFolderID from BT-04
    contract_folder_id = get_contract_folder_id(root, ns)
    if contract_folder_id:
        ocds_data["tender"]["id"] = contract_folder_id

    # Combined Date and Time handling for BT-05
    issue_date_time = get_issue_date_time(root, ns)
    if issue_date_time:
        ocds_data["date"] = issue_date_time

    # Handle ProcurementLegislationDocumentReference
    legal_basis_data = get_legal_basis(root, ns)
    if legal_basis_data:
        ocds_data["tender"]["legalBasis"] = legal_basis_data

    # Handle Lot Strategic Procurement
    lots = get_lot_strategic_procurement(root, ns)
    if lots:
        ocds_data["tender"]["lots"] = lots

    # Cross Border Law from BT-09(b)
    cross_border_law_description = get_cross_border_law(root, ns)
    if cross_border_law_description:
        ocds_data["tender"]["crossBorderLaw"] = cross_border_law_description
    
    # Handle Buyer Activity Authority
    buyer_activity_authority = get_buyer_activity_authority(root, ns)
    if buyer_activity_authority:
        ocds_data["parties"] = [
            {
                "id": "BUYER_ID",  # Replace with the actual buyer ID if available
                "details": {
                    "classifications": [buyer_activity_authority]
                }
            }
        ]

    # Handle Procedure Type (BT-105)
    procedure_type_data = get_procedure_type(root, ns)
    if procedure_type_data:
        ocds_data["tender"].update(procedure_type_data)    

    procedure_type_data = get_procedure_type(root, ns)
    if procedure_type_data:
        ocds_data["tender"].update(procedure_type_data)
    
    # Cross Border Law from BT-09(b)
    cross_border_law_description = get_cross_border_law(root, ns)
    if cross_border_law_description:
        ocds_data["tender"]["crossBorderLaw"] = cross_border_law_description

    # Check if any buyer details should be added to the parties array
    buyer_details = get_buyer_details(root, ns)
    if buyer_details:
        ocds_data["parties"].append(buyer_details)


    # Check and clean if tender or legalBasis is empty
    if "legalBasis" in ocds_data["tender"] and not ocds_data["tender"]["legalBasis"]:
        del ocds_data["tender"]["legalBasis"]
    if not ocds_data["tender"]:
        del ocds_data["tender"]

    return ocds_data








"""


import uuid
import json
from datetime import datetime

# Function to create a new release
def create_release(notice_id, is_pin_only):
    release = {
        "id": notice_id,
        "initiationType": "tender",
        "ocid": "",
        "relatedProcesses": [],
        "parties": [],
        "tender": {
            "documents": [],
            "participationFees": [],
            "lots": [],
            "lotGroups": [],
            "items": []
        },
        "bids": {
            "statistics": [],
            "details": []
        },
        "awards": [],
        "contracts": []
    }

    if is_pin_only:
        release["ocid"] = f"ocds-prefix-{str(uuid.uuid4())}"
    else:
        # Set ocid based on previous publication
        release["ocid"] = "previous-ocid"

    return release

# Function to convert a date to ISO format
def convert_date_to_iso(date_str):
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    return date_obj.strftime("%Y-%m-%dT%H:%M:%SZ")

# Function to add a complaints statistic
def add_complaints_statistic(release, lot_id, statistic_id):
    statistic = {
        "relatedLot": lot_id,
        "scope": "complaints",
        "id": str(statistic_id)
    }
    release["statistics"].append(statistic)

# Function to add a bids statistic
def add_bids_statistic(release, lot_id, statistic_id):
    statistic = {
        "relatedLot": lot_id,
        "id": str(statistic_id)
    }
    release["bids"]["statistics"].append(statistic)

# Function to get or create a document for a document reference
def get_or_create_document(release, document_id):
    for document in release["tender"]["documents"]:
        if document["id"] == document_id:
            return document
    
    new_document = {"id": document_id}
    release["tender"]["documents"].append(new_document)
    return new_document

# Function to get or create a participation fee for a document
def get_or_create_participation_fee(release, document_id, lot_id=None):
    if lot_id:
        lot = next((lot for lot in release["tender"]["lots"] if lot["id"] == lot_id), None)
        if lot:
            for fee in lot["participationFees"]:
                if fee["id"] == document_id:
                    return fee
            
            new_fee = {"id": document_id}
            lot["participationFees"].append(new_fee)
            return new_fee
    else:
        for fee in release["tender"]["participationFees"]:
            if fee["id"] == document_id:
                return fee
        
        new_fee = {"id": document_id}
        release["tender"]["participationFees"].append(new_fee)
        return new_fee

# Function to get or create an organization for a company
def get_or_create_organization(release, organization_id):
    for organization in release["parties"]:
        if organization["id"] == organization_id:
            return organization
    
    new_organization = {
        "id": organization_id,
        "identifier": {},
        "roles": []
    }
    release["parties"].append(new_organization)
    return new_organization

# Function to get or create a lot for a ProcurementProjectLot
def get_or_create_lot(release, lot_id):
    for lot in release["tender"]["lots"]:
        if lot["id"] == lot_id:
            return lot
    
    new_lot = {"id": lot_id}
    release["tender"]["lots"].append(new_lot)
    return new_lot

# Function to get or create an item for
def create_release(notice_id, is_pin_only, previous_ocid=None):
    release = {
        "id": notice_id,
        "initiationType": "tender",
        "ocid": "",
        "relatedProcesses": [],
        "parties": [],
        "tender": {
            "documents": [],
            "participationFees": [],
            "lots": [],
            "lotGroups": [],
            "items": []
        },
        "bids": {
            "statistics": [],
            "details": []
        },
        "awards": [],
        "contracts": []
    }

    if is_pin_only:
        release["ocid"] = f"ocds-prefix-{str(uuid.uuid4())}"
    elif previous_ocid:
        release["ocid"] = previous_ocid
    else:
        release["ocid"] = "previous-ocid"

    return release

def convert_date_to_iso(date_str):
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    return date_obj.strftime("%Y-%m-%dT%H:%M:%SZ")

def add_complaints_statistic(release, lot_id, statistic_id):
    statistic = {
        "relatedLot": lot_id,
        "scope": "complaints",
        "id": str(statistic_id)
    }
    release["statistics"].append(statistic)

def add_bids_statistic(release, lot_id, statistic_id):
    statistic = {
        "relatedLot": lot_id,
        "id": str(statistic_id)
    }
    release["bids"]["statistics"].append(statistic)

def get_or_create_document(release, document_id):
    for document in release["tender"]["documents"]:
        if document["id"] == document_id:
            return document
    new_document = {"id": document_id}
    release["tender"]["documents"].append(new_document)
    return new_document

def get_or_create_participation_fee(release, document_id, lot_id=None):
    if lot_id:
        lot = next((lot for lot in release["tender"]["lots"] if lot["id"] == lot_id), None)
        if lot:
            for fee in lot["participationFees"]:
                if fee["id"] == document_id:
                    return fee
            new_fee = {"id": document_id}
            lot["participationFees"].append(new_fee)
            return new_fee
    else:
        for fee in release["tender"]["participationFees"]:
            if fee["id"] == document_id:
                return fee
        new_fee = {"id": document_id}
        release["tender"]["participationFees"].append(new_fee)
        return new_fee

def get_or_create_organization(release, organization_id):
    for organization in release["parties"]:
        if organization["id"] == organization_id:
            return organization
    new_organization = {
        "id": organization_id,
        "identifier": {},
        "roles": []
    }
    release["parties"].append(new_organization)
    return new_organization

def get_or_create_lot(release, lot_id):
    for lot in release["tender"]["lots"]:
        if lot["id"] == lot_id:
            return lot
    new_lot = {"id": lot_id}
    release["tender"]["lots"].append(new_lot)
    return new_lot

def process_pin_notice(eform_xml, lookup_form_type):
    root = etree.fromstring(eform_xml)
    ns = {
        'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
        'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2'
    }

    for part in root.findall(".//cac:ProcurementProjectLot[cbc:ID/@schemeName='Part']", namespaces=ns):
        part_id = part.find("cbc:ID", namespaces=ns).text

        # Create a new release for each part
        release = create_release(part_id, is_pin_only=True)

        # Process other data and update the release
        # ...

        # Return or yield the release

def process_non_pin_notice(eform_xml, lookup_form_type):
    root = etree.fromstring(eform_xml)
    ns = {
        'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
        'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2'
    }

    notice_id = root.find("cbc:ID", namespaces=ns).text

    # Determine if it's a new procedure or a continuation
    is_new_procedure = ...  # Add logic to determine if it's a new procedure

    if is_new_procedure:
        release = create_release(notice_id, is_pin_only=False)
    else:
        previous_ocid = ...  # Get the previous OCID from somewhere
        release = create_release(notice_id, is_pin_only=False, previous_ocid=previous_ocid)

    # Process other data and update the release
    # ...

    return release



import json

ocds_json = json.dumps(ocds_release, indent=2)
with open('output_ocds_data.json', 'w') as f:
    f.write(ocds_json)



from your_script import process_pin_notice, process_non_pin_notice, lookup_form_type
import os

# Iterate over XML files in a directory
for filename in os.listdir('path/to/eu_ted_xml_files'):
    if filename.endswith('.xml'):
        with open(os.path.join('path/to/eu_ted_xml_files', filename), 'r') as f:
            eu_ted_xml = f.read()

        # Determine if it's a PIN notice or non-PIN notice
        is_pin_notice = ... # Add your logic to determine if it's a PIN notice

        if is_pin_notice:
            ocds_release = process_pin_notice(eu_ted_xml, lookup_form_type)
        else:
            ocds_release = process_non_pin_notice(eu_ted_xml, lookup_form_type)

        # Process or output the OCDS release
        # ...


"""        