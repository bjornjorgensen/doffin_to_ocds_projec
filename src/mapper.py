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

            # Check for GPA coverage and optionally create 'coveredBy'
            gpa_indicator_element = lot.find(".//cac:TenderingProcess/cbc:GovernmentAgreementConstraintIndicator", namespaces=ns)
            if gpa_indicator_element is not None and gpa_indicator_element.text.strip().lower() == 'true':
                lot_data['coveredBy'] = ['GPA']  # Create 'coveredBy' and populate with 'GPA'

            # Framework agreement processing
            framework_agreement = lot.find(".//cac:TenderingProcess/cac:FrameworkAgreement", namespaces=ns)
            if framework_agreement is not None:
                fa_data = {}

                justification_element = framework_agreement.find(".//cbc:Justification", namespaces=ns)
                if justification_element is not None:
                    fa_data['periodRationale'] = justification_element.text

                buyer_categories_element = framework_agreement.find(".//cac:SubsequentProcessTenderRequirement[cbc:Name='buyer-categories']/cbc:Description", namespaces=ns)
                if buyer_categories_element is not None:
                    fa_data['buyerCategories'] = buyer_categories_element.text
                
                max_participants_element = framework_agreement.find(".//cbc:MaximumOperatorQuantity", namespaces=ns)
                if max_participants_element is not None:
                    fa_data['maximumParticipants'] = int(max_participants_element.text)
                
                if fa_data:
                    lot_data['techniques'] = {'frameworkAgreement': fa_data}

            # Sustainability and strategic procurement processing
            procurement_project = lot.find("cac:ProcurementProject", namespaces=ns)
            if procurement_project is not None and len(procurement_project) > 0:
                procurement_types = procurement_project.findall("cac:ProcurementAdditionalType/cbc:ProcurementTypeCode[@listName='strategic-procurement']", namespaces=ns)
                for procurement_type in procurement_types:
                    code = procurement_type.text
                    if code != "none":
                        lot_data["hasSustainability"] = True
                        sustainability_goal = STRATEGIC_PROCUREMENT_MAPPING.get(code, None)
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

def is_gpa_covered(root, ns):
    gpa_indicator = root.find(".//cac:TenderingProcess/cbc:GovernmentAgreementConstraintIndicator", namespaces=ns)
    return gpa_indicator is not None and gpa_indicator.text.lower() == 'true'

def get_dps_termination(root, ns):
    """
    Processes the dynamic purchasing system termination based on e-form XML data. 
    """
    lot_results = []
    notice_results = root.findall(".//efext:EformsExtension/efac:NoticeResult", namespaces=ns)
    
    for notice_result in notice_results:
        dps_termination_indicator = notice_result.find(".//efbc:DPSTerminationIndicator", namespaces=ns)
        if dps_termination_indicator is not None and dps_termination_indicator.text.strip().lower() == 'true':
            tender_lot_id = notice_result.find(".//efac:TenderLot/cbc:ID[@schemeName='Lot']", namespaces=ns)
            if tender_lot_id is not None:
                lot_results.append({
                    "id": tender_lot_id.text,
                    "techniques": {"dynamicPurchasingSystem": {"status": "terminated"}}
                })

    return lot_results

def integrate_lot_data(existing_lots, dps_termination_lots):
    """
    Integrates DPS termination data into existing lot data.
    """
    lot_id_set = set(lot["id"] for lot in dps_termination_lots)
    for lot in existing_lots:
        if lot["id"] in lot_id_set:
            if "techniques" not in lot:
                lot["techniques"] = {}
            lot["techniques"]["dynamicPurchasingSystem"] = {"status": "terminated"}
    for dps_lot in dps_termination_lots:
        if dps_lot["id"] not in lot_id_set:
            existing_lots.append(dps_lot)
    return existing_lots

def get_no_negotiation_necessary(root, ns):
    lots_no_negotiation = []
    for lot in root.findall(".//cac:ProcurementProjectLot", namespaces=ns):
        lot_id_element = lot.find(".//cbc:ID[@schemeName='Lot']", namespaces=ns)
        no_negotiation_indicator = lot.find(".//cac:TenderingTerms/cac:AwardingTerms/cbc:NoFurtherNegotiationIndicator", namespaces=ns)
        if lot_id_element is not None and no_negotiation_indicator is not None and no_negotiation_indicator.text.strip().lower() == 'true':
            lots_no_negotiation.append({
                "id": lot_id_element.text,
                "secondStage": {
                    "noNegotiationNecessary": True
                }
            })
    return lots_no_negotiation

def integrate_no_negotiation_data(existing_lots, no_negotiation_lots):
    """
    Integrates no negotiation necessary data into existing lot data.
    """
    no_negotiation_lot_ids = {lot["id"]: lot for lot in no_negotiation_lots}
    for lot in existing_lots:
        if lot["id"] in no_negotiation_lot_ids:
            if "secondStage" not in lot:
                lot["secondStage"] = {}
            lot["secondStage"]["noNegotiationNecessary"] = True
    return existing_lots

def get_electronic_auction_description(root, ns):
    """
    Extracts electronic auction descriptions from the XML and integrates them into the lot descriptions.
    """
    electronic_auction_descriptions = []
    for lot in root.findall(".//cac:ProcurementProjectLot", namespaces=ns):
        lot_id_element = lot.find(".//cbc:ID[@schemeName='Lot']", namespaces=ns)
        auction_description_element = lot.find(".//cac:TenderingProcess/cac:AuctionTerms/cbc:Description", namespaces=ns)
        
        if lot_id_element is not None and auction_description_element is not None:
            electronic_auction_descriptions.append({
                "id": lot_id_element.text,
                "techniques": {
                    "electronicAuction": {
                        "description": auction_description_element.text
                    }
                }
            })
    return electronic_auction_descriptions

def integrate_electronic_auction_data(existing_lots, electronic_auction_data):
    """
    Integrates electronic auction data into existing lot data.
    """
    auction_lot_ids = {lot["id"]: lot for lot in electronic_auction_data}
    for lot in existing_lots:
        if lot["id"] in auction_lot_ids:
            if "techniques" not in lot:
                lot["techniques"] = {}
            lot["techniques"]["electronicAuction"] = auction_lot_ids[lot["id"]]["techniques"]["electronicAuction"]
    return existing_lots

def eform_to_ocds(eform_xml, lookup_form_type):
    root = etree.fromstring(eform_xml)
    ns = {
        'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
        'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
        'ext': 'urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2',
        'efext': 'urn:oasis:names:specification:eforms:extensions:schema:xsd:CommonExtensionComponents-1',
        'efac': 'urn:oasis:names:specification:eforms:extensions:schema:xsd:CommonAggregateComponents-1',
        'efbc': 'urn:oasis:names:specification:eforms:extensions:schema:xsd:CommonBasicComponents-1'
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

    if is_gpa_covered(root, ns):
        ocds_data["tender"]["coveredBy"] = ["GPA"]

    dps_termination_lots = get_dps_termination(root, ns)
    if dps_termination_lots:
        if "lots" in ocds_data.get("tender", {}):
            ocds_data["tender"]["lots"] = integrate_lot_data(ocds_data["tender"]["lots"], dps_termination_lots)
        else:
            ocds_data["tender"]["lots"] = dps_termination_lots 
            
    # Handling No Negotiation Necessary
    no_negotiation_lots = get_no_negotiation_necessary(root, ns)
    if no_negotiation_lots:
        if "lots" in ocds_data.get("tender", {}):
            ocds_data["tender"]["lots"] = integrate_no_negotiation_data(ocds_data["tender"]["lots"], no_negotiation_lots)
        else:
            ocds_data["tender"]["lots"] = no_negotiation_lots   

    electronic_auction_lots = get_electronic_auction_description(root, ns)
    if electronic_auction_lots:
        if "lots" in ocds_data.get("tender", {}):
            ocds_data["tender"]["lots"] = integrate_electronic_auction_data(ocds_data["tender"]["lots"], electronic_auction_lots)
        else:
            ocds_data["tender"]["lots"] = electronic_auction_lots
    # Check and clean if tender or legalBasis is empty
    if "legalBasis" in ocds_data["tender"] and not ocds_data["tender"]["legalBasis"]:
        del ocds_data["tender"]["legalBasis"]
    if not ocds_data["tender"]:
        del ocds_data["tender"]

    return ocds_data




def create_release(ocds_data):
    tender = ocds_data.get("tender", {})
    parties = ocds_data.get("parties", [])
    # Check if a new ocid needs to be assigned
    assign_new_ocid = False
    if "tag" in ocds_data and ocds_data["tag"] in ["priorInformation", "periodicIndicative"]:
        assign_new_ocid = True
    elif "tag" in ocds_data and ocds_data["tag"] == "contractAward":
        assign_new_ocid = True
    elif not tender.get("id"):
        assign_new_ocid = True
    if assign_new_ocid:
        ocid = f"ocds-prefix-{str(uuid.uuid4())}"  # Replace 'ocds-prefix-' with your OCID prefix
    else:
        ocid = tender.get("id")
    release = {
        "id": tender.get("id"),
        "initiationType": "tender",
        "ocid": ocid,
        "parties": parties,
        "tender": tender
    }
    # Handle lots
    if "lots" in tender:
        lots = []
        for lot in tender["lots"]:
            lot_release = {
                "id": lot.get("id"),
                "initiationType": "tender",
                "ocid": ocid,
                "parties": parties,
                "tender": {
                    "id": lot.get("id"),
                    "lots": [lot]
                }
            }
            lots.append(lot_release)
        return lots
    return [release]

