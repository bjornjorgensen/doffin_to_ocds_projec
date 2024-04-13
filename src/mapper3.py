from lxml import etree
from collections import defaultdict


FORM_TYPE_MAPPING = {
    "competition": {"tag": ["tender"], "status": "active"},
    # Add additional mappings as necessary
}


STRATEGIC_PROCUREMENT_MAPPING = {
    "inn-pur": "economic.innovativePurchase"
    # Add any required mappings if necessary
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
        lot_id_element = lot.find("cbc:ID", namespaces=ns)
        if lot_id_element is not None and lot_id_element.get("schemeName") == "Lot":
            lot_id = lot_id_element.text
            lot_data = {
                "id": lot_id,
                "hasSustainability": False,
                "sustainability": []
            }
            procurement_project = lot.find("cac:ProcurementProject", namespaces=ns)
            if procurement_project is not None:
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
    Extracts the Cross Border Law description, if available.
    """
    cross_border_law_element = root.find(".//cac:TenderingTerms/cac:ProcurementLegislationDocumentReference[cbc:ID='CrossBorderLaw']/cbc:DocumentDescription", namespaces=ns)
    if cross_border_law_element is not None:
        return cross_border_law_element.text  # Assumes that there's only one such description
    return None

def eform_to_ocds(eform_xml, lookup_form_type):
    root = etree.fromstring(eform_xml)
    ocds_data = {"tender": {}}
    ns = {
        'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
        'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2'
    }

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
    
    # Check and clean if tender or legalBasis is empty
    if "legalBasis" in ocds_data["tender"] and not ocds_data["tender"]["legalBasis"]:
        del ocds_data["tender"]["legalBasis"]
    if not ocds_data["tender"]:
        del ocds_data["tender"]

    return ocds_data