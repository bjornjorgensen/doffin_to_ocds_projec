from lxml import etree
from dateutil import parser

# Define namespace mappings
namespaces = {
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "ext": "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",
    "efext": "urn:edigrampelayo:names:specification:eforms:extensions:eformsext",
    "efac": "urn:edigrampelayo:names:specification:eforms:aggregatecomponents",
    "efbc": "urn:edigrampelayo:names:specification:eforms:basiccomponents"
}

# Form type mapping table
form_type_mapping = {
    "competition": {
        "release_tag": ["tender"],
        "tender_status": "active"
    },
    # Add more mappings as needed
}

# Strategic procurement mapping table
strategic_procurement_mapping = {
    "env-pur": "environmental",
    "inn-pur": "economic.innovativePurchase",
    "soc-pur": "social"
}

# Procurement procedure type mapping table
procurement_procedure_type_mapping = {
    "open": "open",
    "restricted": "restricted",
    # Add more mappings as needed
}

def map_legal_basis(root):
    legal_basis_nodes = root.findall(".//cac:TenderingTerms/cac:ProcurementLegislationDocumentReference", namespaces=namespaces)
    legal_basis = []
    for node in legal_basis_nodes:
        legal_basis_entry = {}
        id_node = node.find(".//cbc:ID[@schemeName='ELI']", namespaces=namespaces)
        if id_node is not None:
            legal_basis_entry["scheme"] = "ELI"
            legal_basis_entry["id"] = id_node.text

        description_node = node.find(".//cbc:DocumentDescription", namespaces=namespaces)
        if description_node is not None:
            legal_basis_entry["description"] = description_node.text

        no_id_node = node.find(".//cbc:ID[.='LocalLegalBasis']", namespaces=namespaces)
        if no_id_node is not None:
            legal_basis_entry["id"] = "LocalLegalBasis"
            # Reuse the previously found description_node since it follows the same structure
            if description_node is not None:
                legal_basis_entry["description"] = description_node.text

        if legal_basis_entry:
            legal_basis.append(legal_basis_entry)

    # Check for BT-09(a)-Procedure Cross Border Law and BT-09(b)-Procedure Cross Border Law Description
    cross_border_law_node = root.find(".//cac:TenderingTerms/cac:ProcurementLegislationDocumentReference[cbc:ID/text()='CrossBorderLaw']", namespaces=namespaces)
    if cross_border_law_node is not None:
        cross_border_law_description_node = cross_border_law_node.find("cbc:DocumentDescription", namespaces=namespaces)
        if cross_border_law_description_node is not None:
            cross_border_law_entry = {
                "crossBorderLaw": cross_border_law_description_node.text
            }
            legal_basis.append(cross_border_law_entry)

    # Check for BT-01-notice * Procedure Legal Basis
    regulatory_domain_node = root.find(".//cbc:RegulatoryDomain", namespaces=namespaces)
    if regulatory_domain_node is not None:
        legal_basis_entry = {
            "scheme": "CELEX",
            "id": regulatory_domain_node.text
        }
        legal_basis.append(legal_basis_entry)

    return legal_basis

def map_strategic_procurement(root):
    strategic_procurement = []
    lot_nodes = root.findall(".//cac:ProcurementProjectLot[cbc:ID/@schemeName='Lot']", namespaces=namespaces)
    for lot_node in lot_nodes:
        lot_id = lot_node.find("cbc:ID", namespaces=namespaces).text
        project_node = lot_node.find("cac:ProcurementProject", namespaces=namespaces)
        if project_node is not None:
            additional_type_nodes = project_node.findall("cac:ProcurementAdditionalType[cbc:ProcurementTypeCode/@listName='strategic-procurement']", namespaces=namespaces)
            for additional_type_node in additional_type_nodes:
                code_node = additional_type_node.find("cbc:ProcurementTypeCode", namespaces=namespaces)
                if code_node is not None:
                    code = code_node.text
                    if code != "none":
                        sustainability_entry = {
                            "lot": {
                                "id": lot_id,
                                "hasSustainability": True
                            },
                            "sustainability": {
                                "goal": strategic_procurement_mapping.get(code, ""),
                                "strategies": ["awardCriteria", "contractPerformanceConditions", "selectionCriteria", "technicalSpecifications"]
                            }
                        }
                        strategic_procurement.append(sustainability_entry)

    return strategic_procurement

def map_contracting_parties(root):
    contracting_parties = []
    party_nodes = root.findall(".//cac:ContractingParty", namespaces=namespaces)
    for party_node in party_nodes:
        party_entry = {}

        party_id_node = party_node.find("cac:Party/cac:PartyIdentification/cbc:ID[@schemeName='organization']", namespaces=namespaces)
        if party_id_node is not None:
            party_entry["id"] = party_id_node.text
            party_entry["details"] = {
                "classifications": []
            }

        # Handle BT-10-Procedure-Buyer * Activity Authority
        activity_type_code_node = party_node.find("cac:ContractingActivity/cbc:ActivityTypeCode[@listName='authority-activity']", namespaces=namespaces)
        if activity_type_code_node is not None:
            activity_type_code = activity_type_code_node.text
            classification_entry = {}
            if "COFOG" in activity_type_code_node.get("listURI"):
                classification_entry["description"] = activity_type_code
                classification_entry["scheme"] = "COFOG"
            # Look up the code's number in the UN Classifications on Economic Statistics and map it to the classification's .id
            else:
                classification_entry["id"] = activity_type_code
                classification_entry["scheme"] = "eu-main-activity"
            # Look up the code's label in the authority table and map it to the classification's .description
            party_entry["details"]["classifications"].append(classification_entry)

        # Handle BT-11-Procedure-Buyer * Buyer Legal Type
        party_type_code_node = party_node.find("cac:ContractingPartyType/cbc:PartyTypeCode[@listName='buyer-legal-type']", namespaces=namespaces)
        if party_type_code_node is not None:
            party_type_code = party_type_code_node.text
            classification_entry = {
                "id": party_type_code,
                "scheme": "TED_CA_TYPE"
            }
            # Look up the code's label in the authority table and map it to the classification's .description
            party_entry["details"]["classifications"].append(classification_entry)

        if party_entry:
            contracting_parties.append(party_entry)

    return contracting_parties


def sanitize_datetime_string(dt_string):
    parts = dt_string.split('T')
    if len(parts) == 2 and '+' in parts[0]:
        date_part, time_part = parts
        date_part, timezone = date_part.split('+', 1)
        corrected_dt_string = f"{date_part}T{time_part}+{timezone}"
        return corrected_dt_string
    return dt_string

def convert_eform_to_ocds(eform_xml):
    root = etree.fromstring(eform_xml.encode('utf-8'))
    ocds_release = {
        "tag": [],
        "tender": {}
    }
    
    # Discard BT-02-notice * Notice Type as per instructions
    notice_type_node = root.find(".//cbc:NoticeTypeCode", namespaces=namespaces)
    if notice_type_node is not None:
        print(f"Discarding BT-02-notice * Notice Type: {notice_type_node.text}")

    # Handle BT-03-notice * Form Type
    form_type_node = root.find(".//cbc:NoticeTypeCode", namespaces=namespaces)
    if form_type_node is not None:
        form_type = form_type_node.get("{http://www.w3.org/XML/1998/namespace}listName")
        if form_type in form_type_mapping:
            ocds_release["tag"].extend(form_type_mapping[form_type]["release_tag"])
            ocds_release["tender"]["status"] = form_type_mapping[form_type]["tender_status"]
    
    # Handle BT-04-notice * Procedure Identifier
    contract_folder_id_node = root.find(".//cbc:ContractFolderID", namespaces=namespaces)
    if contract_folder_id_node is not None:
        ocds_release["tender"]["id"] = contract_folder_id_node.text
    
    # Handle BT-05(a)-notice * Notice Dispatch Date and BT-05(b)-notice * Notice Dispatch Time
    issue_date_node = root.find(".//cbc:IssueDate", namespaces=namespaces)
    issue_time_node = root.find(".//cbc:IssueTime", namespaces=namespaces)
    if issue_date_node is not None and issue_time_node is not None:
        issue_date = issue_date_node.text
        issue_time = issue_time_node.text
        combined_datetime = f"{issue_date}T{issue_time}"
        
        # Sanitize the combined_datetime string to correct format before parsing
        combined_datetime = sanitize_datetime_string(combined_datetime)
        
        # Parse and set the date in the OCDS release dictionary
        ocds_release["date"] = parser.parse(combined_datetime).isoformat()

    ocds_release["tender"]["legalBasis"] = map_legal_basis(root)
    ocds_release["tender"]["lots"] = map_strategic_procurement(root)
    ocds_release["parties"] = map_contracting_parties(root)

    # Handle BT-105-Procedure * Procedure Type
    procedure_code_node = root.find(".//cac:TenderingProcess/cbc:ProcedureCode", namespaces=namespaces)
    if procedure_code_node is not None:
        procedure_code = procedure_code_node.text
        procedure_mapping = procurement_procedure_type_mapping.get(procedure_code, None)
        if procedure_mapping:
            ocds_release["tender"]["procurementMethod"] = procedure_mapping
            ocds_release["tender"]["procurementMethodDetails"] = procedure_code

    # Handle BT-106-Procedure * Procedure Accelerated
    accelerated_procedure_node = root.find(".//cac:TenderingProcess/cac:ProcessJustification[cbc:ProcessReasonCode/@listName='accelerated-procedure']/cbc:ProcessReasonCode", namespaces=namespaces)
    if accelerated_procedure_node is not None:
        accelerated_procedure_value = accelerated_procedure_node.text.lower() == "true"
        ocds_release["tender"]["procedure"] = {
            "isAccelerated": accelerated_procedure_value
        }

    # Handle BT-109-Lot Framework Duration Justification
    lot_nodes = root.findall(".//cac:ProcurementProjectLot[cbc:ID/@schemeName='Lot']", namespaces=namespaces)
    for lot_node in lot_nodes:
        lot_id = lot_node.find("cbc:ID", namespaces=namespaces).text
        justification_node = lot_node.find("cac:TenderingProcess/cac:FrameworkAgreement/cbc:Justification", namespaces=namespaces)
        if justification_node is not None:
            for lot in ocds_release["tender"]["lots"]:
                if lot["id"] == lot_id:
                    lot["techniques"] = {
                        "frameworkAgreement": {
                            "periodRationale": justification_node.text
                        }
                    }

    # Handle BT-111-Lot Framework Buyer Categories
    for lot_node in lot_nodes:
        lot_id = lot_node.find("cbc:ID", namespaces=namespaces).text
        buyer_categories_node = lot_node.find("cac:TenderingProcess/cac:FrameworkAgreement/cac:SubsequentProcessTenderRequirement[cbc:Name/text()='buyer-categories']/cbc:Description", namespaces=namespaces)
        if buyer_categories_node is not None:
            for lot in ocds_release["tender"]["lots"]:
                if lot["id"] == lot_id:
                    lot["techniques"]["frameworkAgreement"]["buyerCategories"] = buyer_categories_node.text

    # Discard BT-1118-NoticeResult Notice Framework Approximate Value

    # Handle BT-118-NoticeResult * Notice Framework Maximum Value
    notice_result_node = root.find(".//efext:EformsExtension/efac:NoticeResult", namespaces=namespaces)
    if notice_result_node is not None:
        max_framework_amount_node = notice_result_node.find("efbc:OverallMaximumFrameworkContractsAmount", namespaces=namespaces)
        if max_framework_amount_node is not None:
            print(f"Discarding BT-118-NoticeResult * Notice Framework Maximum Value: {max_framework_amount_node.text}")

    # Handle BT-119-LotResult Dynamic Purchasing System Termination
    lot_result_nodes = root.findall(".//efext:EformsExtension/efac:NoticeResult/efac:LotResult", namespaces=namespaces)
    for lot_result_node in lot_result_nodes:
        dps_termination_node = lot_result_node.find("efbc:DPSTerminationIndicator", namespaces=namespaces)
        if dps_termination_node is not None and dps_termination_node.text.lower() == "true":
            lot_id_node = lot_result_node.find("efac:TenderLot/cbc:ID[@schemeName='Lot']", namespaces=namespaces)
            if lot_id_node is not None:
                lot_id = lot_id_node.text
                for lot in ocds_release["tender"]["lots"]:
                    if lot["id"] == lot_id:
                        lot["techniques"] = lot.get("techniques", {})
                        lot["techniques"]["dynamicPurchasingSystem"] = {
                            "status": "terminated"
                        }

    # Handle BT-113-Lot Framework Maximum Participants Number
    for lot_node in lot_nodes:
        lot_id = lot_node.find("cbc:ID", namespaces=namespaces).text
        maximum_operator_quantity_node = lot_node.find("cac:TenderingProcess/cac:FrameworkAgreement/cbc:MaximumOperatorQuantity", namespaces=namespaces)
        if maximum_operator_quantity_node is not None:
            for lot in ocds_release["tender"]["lots"]:
                if lot["id"] == lot_id:
                    lot["techniques"]["frameworkAgreement"]["maximumParticipants"] = int(maximum_operator_quantity_node.text)

    # Handle BT-115-Lot * GPA Coverage
    for lot_node in lot_nodes:
        lot_id = lot_node.find("cbc:ID", namespaces=namespaces).text
        gpa_coverage_node = lot_node.find("cac:TenderingProcess/cbc:GovernmentAgreementConstraintIndicator",namespaces=namespaces)
        if gpa_coverage_node is not None and gpa_coverage_node.text.lower() == "true": 
            for lot in ocds_release["tender"]["lots"]: 
                if lot["id"] == lot_id: lot["coveredBy"] = ["GPA"]


    # Handle BT-115-Part GPA Coverage
    gpa_coverage_node = root.find(".//cac:TenderingProcess/cbc:GovernmentAgreementConstraintIndicator", namespaces=namespaces)
    if gpa_coverage_node is not None and gpa_coverage_node.text.lower() == "true":
        ocds_release["tender"]["coveredBy"] = ["GPA"]

    # Handle BT-120-Lot No Negotiation Necessary
    for lot_node in lot_nodes:
        lot_id = lot_node.find("cbc:ID", namespaces=namespaces).text
        no_negotiation_node = lot_node.find("cac:TenderingTerms/cac:AwardingTerms/cbc:NoFurtherNegotiationIndicator", namespaces=namespaces)
        if no_negotiation_node is not None and no_negotiation_node.text.lower() == "true":
            for lot in ocds_release["tender"]["lots"]:
                if lot["id"] == lot_id:
                    lot["secondStage"] = {
                        "noNegotiationNecessary": True
                    }

    # Handle BT-122-Lot Electronic Auction Description
    for lot_node in lot_nodes:
        lot_id = lot_node.find("cbc:ID", namespaces=namespaces).text
        auction_terms_node = lot_node.find("cac:TenderingProcess/cac:AuctionTerms", namespaces=namespaces)
        if auction_terms_node is not None:
            description_node = auction_terms_node.find("cbc:Description", namespaces=namespaces)
            if description_node is not None:
                for lot in ocds_release["tender"]["lots"]:
                    if lot["id"] == lot_id:
                        lot["techniques"] = lot.get("techniques", {})
                        lot["techniques"]["electronicAuction"] = {
                            "description": description_node.text
                        }

    # Handle BT-123-Lot Electronic Auction URL
    for lot_node in lot_nodes:
        lot_id = lot_node.find("cbc:ID", namespaces=namespaces).text
        auction_terms_node = lot_node.find("cac:TenderingProcess/cac:AuctionTerms", namespaces=namespaces)
        if auction_terms_node is not None:
            auction_uri_node = auction_terms_node.find("cbc:AuctionURI", namespaces=namespaces)
            if auction_uri_node is not None:
                for lot in ocds_release["tender"]["lots"]:
                    if lot["id"] == lot_id:
                        lot["techniques"]["electronicAuction"]["url"] = auction_uri_node.text

    # Handle BT-124-Lot Tool Atypical URL and BT-124-Part Tool Atypical URL
    for lot_node in root.findall(".//cac:ProcurementProjectLot", namespaces=namespaces):
        lot_id = lot_node.find("cbc:ID", namespaces=namespaces)
        if lot_id is not None:
            lot_id = lot_id.text
            access_tools_uri_node = lot_node.find("cac:TenderingProcess/cbc:AccessToolsURI", namespaces=namespaces)
            if access_tools_uri_node is not None:
                if lot_id.startswith("Lot"):
                    for lot in ocds_release["tender"]["lots"]:
                        if lot["id"] == lot_id:
                            lot["communication"] = {
                                "atypicalToolUrl": access_tools_uri_node.text
                            }
                else:
                    ocds_release["tender"]["communication"] = {
                        "atypicalToolUrl": access_tools_uri_node.text
                    }

    # Handle BT-125(i)-Lot Previous Planning Identifier and BT-1251-Lot Previous Planning Part Identifier
    lot_nodes = root.findall(".//cac:ProcurementProjectLot[cbc:ID/@schemeName='Lot']", namespaces=namespaces)
    related_processes = []
    for lot_node in lot_nodes:
        lot_id = lot_node.find("cbc:ID", namespaces=namespaces).text
        notice_document_reference_nodes = lot_node.findall("cac:TenderingProcess/cac:NoticeDocumentReference", namespaces=namespaces)
        for notice_document_reference_node in notice_document_reference_nodes:
            id_node = notice_document_reference_node.find("cbc:ID", namespaces=namespaces)
            internal_address_node = notice_document_reference_node.find("cbc:ReferencedDocumentInternalAddress", namespaces=namespaces)
            if id_node is not None:
                related_process = {
                    "id": str(len(related_processes) + 1),
                    "relationship": ["planning"],
                    "scheme": "eu-oj",
                    "identifier": id_node.text,
                    "relatedLots": []
                }
                if internal_address_node is not None:
                    related_process["identifier"] += "-" + internal_address_node.text
                    related_process["relatedLots"].append(internal_address_node.text)
                else:
                    related_process["relatedLots"].append(lot_id)
                related_processes.append(related_process)

    if related_processes:
        ocds_release["relatedProcesses"] = related_processes

    # Handle BT-125(i)-Part Previous Planning Identifier and BT-1251-Part Previous Planning Part Identifier
    part_nodes = root.findall(".//cac:ProcurementProjectLot[cbc:ID/@schemeName='Part']", namespaces=namespaces)
    for part_node in part_nodes:
        notice_document_reference_node = part_node.find("cac:TenderingProcess/cac:NoticeDocumentReference", namespaces=namespaces)
        if notice_document_reference_node is not None:
            id_node = notice_document_reference_node.find("cbc:ID", namespaces=namespaces)
            internal_address_node = notice_document_reference_node.find("cbc:ReferencedDocumentInternalAddress", namespaces=namespaces)
            if id_node is not None:
                related_process = {
                    "id": str(len(ocds_release.get("relatedProcesses", [])) + 1),
                    "relationship": ["planning"],
                    "scheme": "eu-oj"
                }
                if internal_address_node is not None:
                    related_process["identifier"] = f"{id_node.text}-{internal_address_node.text}"
                else:
                    related_process["identifier"] = id_node.text
                ocds_release.setdefault("relatedProcesses", []).append(related_process)

    # Handle BT-1252-Procedure Direct Award Justification Previous Procedure Identifier
    process_justification_nodes = root.findall(".//cac:TenderingProcess/cac:ProcessJustification[cbc:ProcessReasonCode/@listName='direct-award-justification']", namespaces=namespaces)
    for process_justification_node in process_justification_nodes:
        description_node = process_justification_node.find("cbc:Description", namespaces=namespaces)
        if description_node is not None:
            related_process = {
                "id": str(len(ocds_release.get("relatedProcesses", [])) + 1),
                "identifier": description_node.text,
                "scheme": "eu-oj"
            }
            reason_code_node = process_justification_node.find("cbc:ProcessReasonCode", namespaces=namespaces)
            if reason_code_node is not None:
                reason_code = reason_code_node.text
                if reason_code in ["irregular", "unsuitable"]:
                    related_process["relationship"] = ["unsuccessfulProcess"]
                elif reason_code in ["additional", "existing", "repetition"]:
                    related_process["relationship"] = ["prior"]
            ocds_release.setdefault("relatedProcesses", []).append(related_process)

    # Handle BT-127-notice * Future Notice
    planned_date_node = root.find(".//cbc:PlannedDate", namespaces=namespaces)
    if planned_date_node is not None:
        planned_date = planned_date_node.text
        ocds_release["tender"]["communication"] = {
            "futureNoticeDate": dateutil.parser.parse(planned_date).isoformat()
        }

    # Handle BT-13(d)-Lot Additional Information Deadline and BT-13(t)-Lot Additional Information Deadline
    for lot_node in lot_nodes:
        lot_id = lot_node.find("cbc:ID", namespaces=namespaces).text
        info_request_period_node = lot_node.find("cac:TenderingProcess/cac:AdditionalInformationRequestPeriod", namespaces=namespaces)
        if info_request_period_node is not None:
            end_date_node = info_request_period_node.find("cbc:EndDate", namespaces=namespaces)
            end_time_node = info_request_period_node.find("cbc:EndTime", namespaces=namespaces)
            if end_date_node is not None and end_time_node is not None:
                end_date = end_date_node.text
                end_time = end_time_node.text
                combined_datetime = f"{end_date}T{end_time}"
                for lot in ocds_release["tender"]["lots"]:
                    if lot["id"] == lot_id:
                        lot["enquiryPeriod"] = {
                            "endDate": dateutil.parser.parse(combined_datetime).isoformat()
                        }

    # Handle BT-13(d)-Part Additional Information Deadline and BT-13(t)-Part Additional Information Deadline
    info_request_period_node = root.find(".//cac:TenderingProcess/cac:AdditionalInformationRequestPeriod", namespaces=namespaces)
    if info_request_period_node is not None:
        end_date_node = info_request_period_node.find("cbc:EndDate", namespaces=namespaces)
        end_time_node = info_request_period_node.find("cbc:EndTime", namespaces=namespaces)
        if end_date_node is not None and end_time_node is not None:
            end_date = end_date_node.text
            end_time = end_time_node.text
            combined_datetime = f"{end_date}T{end_time}"
            ocds_release["tender"]["enquiryPeriod"] = {
                "endDate": dateutil.parser.parse(combined_datetime).isoformat()
            }

    # Handle BT-130-Lot Dispatch Invitation Tender
    for lot_node in lot_nodes:
        lot_id = lot_node.find("cbc:ID", namespaces=namespaces).text
        invitation_submission_period_node = lot_node.find("cac:TenderingProcess/cac:InvitationSubmissionPeriod", namespaces=namespaces)
        if invitation_submission_period_node is not None:
            start_date_node = invitation_submission_period_node.find("cbc:StartDate", namespaces=namespaces)
            if start_date_node is not None:
                start_date = start_date_node.text
                for lot in ocds_release["tender"]["lots"]:
                    if lot["id"] == lot_id:
                        lot["secondStage"] = lot.get("secondStage", {})
                        lot["secondStage"]["invitationDate"] = dateutil.parser.parse(start_date).isoformat()

    # Handle BT-131(d)-Lot * Deadline Receipt Tenders and BT-131(t)-Lot * Deadline Receipt Tenders
    for lot_node in lot_nodes:
        lot_id = lot_node.find("cbc:ID", namespaces=namespaces).text
        tender_submission_deadline_period_node = lot_node.find("cac:TenderingProcess/cac:TenderSubmissionDeadlinePeriod", namespaces=namespaces)
        if tender_submission_deadline_period_node is not None:
            end_date_node = tender_submission_deadline_period_node.find("cbc:EndDate", namespaces=namespaces)
            end_time_node = tender_submission_deadline_period_node.find("cbc:EndTime", namespaces=namespaces)
            if end_date_node is not None and end_time_node is not None:
                end_date = end_date_node.text
                end_time = end_time_node.text
                combined_datetime = f"{end_date}T{end_time}"
                for lot in ocds_release["tender"]["lots"]:
                    if lot["id"] == lot_id:
                        lot["tenderPeriod"] = {
                            "endDate": dateutil.parser.parse(combined_datetime).isoformat()
                        }

    # Handle BT-1311(d)-Lot * Deadline Receipt Requests and BT-1311(t)-Lot * Deadline Receipt Requests
    for lot_node in lot_nodes:
        lot_id = lot_node.find("cbc:ID", namespaces=namespaces).text
        participation_request_reception_period_node = lot_node.find("cac:TenderingProcess/cac:ParticipationRequestReceptionPeriod", namespaces=namespaces)
        if participation_request_reception_period_node is not None:
            end_date_node = participation_request_reception_period_node.find("cbc:EndDate", namespaces=namespaces)
            end_time_node = participation_request_reception_period_node.find("cbc:EndTime", namespaces=namespaces)
            if end_date_node is not None and end_time_node is not None:
                end_date = end_date_node.text
                end_time = end_time_node.text
                combined_datetime = f"{end_date}T{end_time}"
                for lot in ocds_release["tender"]["lots"]:
                    if lot["id"] == lot_id:
                        lot["tenderPeriod"] = {
                            "endDate": dateutil.parser.parse(combined_datetime).isoformat()
                        }

    # Handle BT-132(d)-Lot Public Opening Date and BT-132(t)-Lot Public Opening Date
    for lot_node in lot_nodes:
        lot_id = lot_node.find("cbc:ID", namespaces=namespaces).text
        open_tender_event_node = lot_node.find("cac:TenderingProcess/cac:OpenTenderEvent", namespaces=namespaces)
        if open_tender_event_node is not None:
            occurrence_date_node = open_tender_event_node.find("cbc:OccurrenceDate", namespaces=namespaces)
            occurrence_time_node = open_tender_event_node.find("cbc:OccurrenceTime", namespaces=namespaces)
            if occurrence_date_node is not None and occurrence_time_node is not None:
                occurrence_date = occurrence_date_node.text
                occurrence_time = occurrence_time_node.text
                combined_datetime = f"{occurrence_date}T{occurrence_time}"
                for lot in ocds_release["tender"]["lots"]:
                    if lot["id"] == lot_id:
                        lot["awardPeriod"] = {
                            "startDate": dateutil.parser.parse(combined_datetime).isoformat()
                            }
                        lot["bidOpening"] = {
                            "date": dateutil.parser.parse(combined_datetime).isoformat()
                            }


    # Handle BT-133-Lot Public Opening Place
    for lot_node in lot_nodes:
        lot_id = lot_node.find("cbc:ID", namespaces=namespaces).text
        open_tender_event_node = lot_node.find("cac:TenderingProcess/cac:OpenTenderEvent", namespaces=namespaces)
        if open_tender_event_node is not None:
            occurrence_location_node = open_tender_event_node.find("cac:OccurenceLocation/cbc:Description", namespaces=namespaces)
            if occurrence_location_node is not None:
                for lot in ocds_release["tender"]["lots"]:
                    if lot["id"] == lot_id:
                        lot["bidOpening"]["location"] = {
                            "description": occurrence_location_node.text
                        }

    # Handle BT-134-Lot Public Opening Description
    for lot_node in lot_nodes:
        lot_id = lot_node.find("cbc:ID", namespaces=namespaces).text
        open_tender_event_node = lot_node.find("cac:TenderingProcess/cac:OpenTenderEvent", namespaces=namespaces)
        if open_tender_event_node is not None:
            description_node = open_tender_event_node.find("cbc:Description", namespaces=namespaces)
            if description_node is not None:
                for lot in ocds_release["tender"]["lots"]:
                    if lot["id"] == lot_id:
                        lot["bidOpening"]["description"] = description_node.text

    # Handle BT-135-Procedure * Direct Award Justification Text
    process_justification_nodes = root.findall(".//cac:TenderingProcess/cac:ProcessJustification[cbc:ProcessReasonCode/@listName='direct-award-justification']", namespaces=namespaces)
    for process_justification_node in process_justification_nodes:
        process_reason_node = process_justification_node.find("cbc:ProcessReason", namespaces=namespaces)
        if process_reason_node is not None:
            ocds_release["tender"]["procurementMethodRationale"] = process_reason_node.text

    # Handle BT-1351-Procedure * Procedure Accelerated Justification
    accelerated_procedure_justification_node = root.find(".//cac:TenderingProcess/cac:ProcessJustification[cbc:ProcessReasonCode/@listName='accelerated-procedure']/cbc:ProcessReason", namespaces=namespaces)
    if accelerated_procedure_justification_node is not None:
        ocds_release["tender"]["procedure"]["acceleratedRationale"] = accelerated_procedure_justification_node.text

    # Handle BT-136-Procedure * Direct Award Justification Code
    process_justification_nodes = root.findall(".//cac:TenderingProcess/cac:ProcessJustification[cbc:ProcessReasonCode/@listName='direct-award-justification']", namespaces=namespaces)
    for process_justification_node in process_justification_nodes:
        process_reason_code_node = process_justification_node.find("cbc:ProcessReasonCode", namespaces=namespaces)
        if process_reason_code_node is not None:
            justification_code = process_reason_code_node.text
            ocds_release["tender"]["procurementMethodRationaleClassifications"] = ocds_release["tender"].get("procurementMethodRationaleClassifications", [])
            classification_entry = {
                "id": justification_code,
                "scheme": "eforms-direct-award-justification"
            }
            # Look up the code's label in the authority table and map it to the classification's .description
            ocds_release["tender"]["procurementMethodRationaleClassifications"].append(classification_entry)

    # Handle BT-137-Lot * Purpose Lot Identifier, BT-137-LotsGroup Purpose Lot Identifier, and BT-137-Part * Purpose Lot Identifier
    lot_nodes = root.findall(".//cac:ProcurementProjectLot", namespaces=namespaces)
    for lot_node in lot_nodes:
        lot_id_node = lot_node.find("cbc:ID", namespaces=namespaces)
        if lot_id_node is not None:
            lot_id = lot_id_node.text
            lot_scheme_name = lot_id_node.get("{http://www.w3.org/XML/1998/namespace}schemeName")
            if lot_scheme_name == "Lot":
                existing_lot = next((lot for lot in ocds_release["tender"].get("lots", []) if lot["id"] == lot_id), None)
                if not existing_lot:
                    ocds_release["tender"]["lots"] = ocds_release["tender"].get("lots", [])
                    ocds_release["tender"]["lots"].append({"id": lot_id})
            elif lot_scheme_name == "LotsGroup":
                existing_lot_group = next((lot_group for lot_group in ocds_release["tender"].get("lotGroups", []) if lot_group["id"] == lot_id), None)
                if not existing_lot_group:
                    ocds_release["tender"]["lotGroups"] = ocds_release["tender"].get("lotGroups", [])
                    ocds_release["tender"]["lotGroups"].append({"id": lot_id})
            elif lot_scheme_name == "Part":
                ocds_release["tender"]["id"] = lot_id

    # Handle BT-13713-LotResult * Result Lot Identifier
    lot_result_nodes = root.findall(".//efext:EformsExtension/efac:NoticeResult/efac:LotResult", namespaces=namespaces)
    for lot_result_node in lot_result_nodes:
        lot_result_id_node = lot_result_node.find("cbc:ID", namespaces=namespaces)
        if lot_result_id_node is not None:
            lot_result_id = lot_result_id_node.get("{http://www.w3.org/XML/1998/namespace}schemeName")
            if lot_result_id == "result":
                award_id = lot_result_id_node.text
                tender_lot_node = lot_result_node.find("efac:TenderLot/cbc:ID[@schemeName='Lot']", namespaces=namespaces)
                if tender_lot_node is not None:
                    tender_lot_id = tender_lot_node.text
                    existing_award = next((award for award in ocds_release.get("awards", []) if award["id"] == award_id), None)
                    if not existing_award:
                        ocds_release["awards"] = ocds_release.get("awards", [])
                        new_award = {
                            "id": award_id,
                            "relatedLots": [tender_lot_id]
                        }
                        ocds_release["awards"].append(new_award)
                    else:
                        if tender_lot_id not in existing_award["relatedLots"]:
                            existing_award["relatedLots"].append(tender_lot_id)

    # Handle BT-13714-Tender * Tender Lot Identifier
    lot_tender_nodes = root.findall(".//efext:EformsExtension/efac:NoticeResult/efac:LotTender", namespaces=namespaces)
    for lot_tender_node in lot_tender_nodes:
        lot_tender_id_node = lot_tender_node.find("cbc:ID", namespaces=namespaces)
        if lot_tender_id_node is not None:
            lot_tender_id = lot_tender_id_node.get("{http://www.w3.org/XML/1998/namespace}schemeName")
            if lot_tender_id == "tender":
                bid_id = lot_tender_id_node.text
                tender_lot_node = lot_tender_node.find("efac:TenderLot/cbc:ID[@schemeName='Lot']", namespaces=namespaces)
                if tender_lot_node is not None:
                    tender_lot_id = tender_lot_node.text
                    existing_bid = next((bid for bid in ocds_release.get("bids", {}).get("details", []) if bid["id"] == bid_id), None)
                    if not existing_bid:
                        ocds_release["bids"] = ocds_release.get("bids", {"details": []})
                        ocds_release["bids"]["details"] = ocds_release["bids"].get("details", [])
                        new_bid = {
                            "id": bid_id,
                            "relatedLots": [tender_lot_id]
                        }
                        ocds_release["bids"]["details"].append(new_bid)
                    else:
                        if tender_lot_id not in existing_bid["relatedLots"]:
                            existing_bid["relatedLots"].append(tender_lot_id)

    # Discard BT-13716-notice Change Previous Section Identifier

    # Handle BT-1375-Procedure Group Lot Identifier
    lot_distribution_nodes = root.findall(".//cac:TenderingTerms/cac:LotDistribution/cac:LotsGroup", namespaces=namespaces)
    for lot_distribution_node in lot_distribution_nodes:
        lot_group_id_node = lot_distribution_node.find("cbc:LotsGroupID", namespaces=namespaces)
        if lot_group_id_node is not None:
            lot_group_id = lot_group_id_node.get("{http://www.w3.org/XML/1998/namespace}schemeName")
            if lot_group_id == "LotsGroup":
                lot_group_id = lot_group_id_node.text
                existing_lot_group = next((lot_group for lot_group in ocds_release["tender"].get("lotGroups", []) if lot_group["id"] == lot_group_id), None)
                if not existing_lot_group:
                    ocds_release["tender"]["lotGroups"] = ocds_release["tender"].get("lotGroups", [])
                    new_lot_group = {
                        "id": lot_group_id,
                        "relatedLots": []
                    }
                    ocds_release["tender"]["lotGroups"].append(new_lot_group)
                    existing_lot_group = new_lot_group
                lot_reference_nodes = lot_distribution_node.findall("cac:ProcurementProjectLotReference/cbc:ID[@schemeName='Lot']", namespaces=namespaces)
                for lot_reference_node in lot_reference_nodes:
                    lot_id = lot_reference_node.text
                    if lot_id not in existing_lot_group["relatedLots"]:
                        existing_lot_group["relatedLots"].append(lot_id)

    # Handle BT-14-Lot * Documents Restricted and BT-14-Part Documents Restricted
    for lot_node in lot_nodes:
        lot_id_node = lot_node.find("cbc:ID", namespaces=namespaces)
        if lot_id_node is not None:
            lot_id = lot_id_node.text
            lot_scheme_name = lot_id_node.get("{http://www.w3.org/XML/1998/namespace}schemeName")
            document_reference_nodes = lot_node.findall("cac:TenderingTerms/cac:CallForTendersDocumentReference[cbc:DocumentType='restricted-document']", namespaces=namespaces)
            for document_reference_node in document_reference_nodes:
                document_id_node = document_reference_node.find("cbc:ID", namespaces=namespaces)
                if document_id_node is not None:
                    document_id = document_id_node.text
                    existing_document = next((document for document in ocds_release["tender"].get("documents", []) if document["id"] == document_id), None)
                    if not existing_document:
                        ocds_release["tender"]["documents"] = ocds_release["tender"].get("documents", [])
                        new_document = {
                            "id": document_id,
                            "documentType": "biddingDocuments",
                            "accessDetails": "Restricted."
                        }
                        if lot_scheme_name == "Lot":
                            new_document["relatedLots"] = [lot_id]
                        ocds_release["tender"]["documents"].append(new_document)
                    else:
                        if lot_scheme_name == "Lot" and lot_id not in existing_document.get("relatedLots", []):
                            existing_document["relatedLots"] = existing_document.get("relatedLots", [])
                            existing_document["relatedLots"].append(lot_id)

    # Handle BT-140-notice * Change Reason Code and BT-141(a)-notice Change Description
    change_nodes = root.findall(".//efext:EformsExtension/efac:Changes/efac:Change", namespaces=namespaces)
    for change_node in change_nodes:
        change_reason_code_node = change_node.find("efac:ChangeReason/cbc:ReasonCode", namespaces=namespaces)
        if change_reason_code_node is not None:
            change_reason_code = change_reason_code_node.text
            change_description_node = change_node.find("efbc:ChangeDescription", namespaces=namespaces)
            change_description = change_description_node.text if change_description_node is not None else None
            changed_section_identifier_node = change_node.find("efac:ChangedSection/efbc:ChangedSectionIdentifier", namespaces=namespaces)
            if changed_section_identifier_node is not None:
                changed_section_identifier = changed_section_identifier_node.text
                if changed_section_identifier.startswith("RES-"):
                    award_id = changed_section_identifier
                    existing_award = next((award for award in ocds_release.get("awards", []) if award["id"] == award_id), None)
                    if existing_award:
                        existing_award["amendments"] = existing_award.get("amendments", [])
                        amendment = {
                            "id": str(len(existing_award["amendments"]) + 1),
                            "rationaleClassifications": [{
                                "id": change_reason_code,
                                "scheme": "eu-change-corrig-justification"
                            }]
                        }
                        if change_description:
                            amendment["description"] = change_description
                        existing_award["amendments"].append(amendment)
                elif changed_section_identifier.startswith("LOT-"):
                    amendment = {
                        "id": str(len(ocds_release["tender"].get("amendments", [])) + 1),
                        "relatedLots": [changed_section_identifier],
                        "rationaleClassifications": [{
                            "id": change_reason_code,
                            "scheme": "eu-change-corrig-justification"
                        }]
                    }
                    if change_description:
                        amendment["description"] = change_description
                    ocds_release["tender"]["amendments"] = ocds_release["tender"].get("amendments", [])
                    ocds_release["tender"]["amendments"].append(amendment)
                elif changed_section_identifier.startswith("GLO-"):
                    amendment = {
                        "id": str(len(ocds_release["tender"].get("amendments", [])) + 1),
                        "relatedLotGroups": [changed_section_identifier],
                        "rationaleClassifications": [{
                            "id": change_reason_code,
                            "scheme": "eu-change-corrig-justification"
                        }]
                    }
                    if change_description: amendment = {
                        "id": str(len(ocds_release["tender"].get("amendments", [])) + 1),
                        "rationaleClassifications": [
                            {
                                "id": change_reason_code,
                                "scheme": "eu-change-corrig-justification"
                            }
                        ],
                        "description": change_description
                    }
                ocds_release["tender"]["amendments"] = ocds_release["tender"].get("amendments", [])
                ocds_release["tender"]["amendments"].append(amendment)
            else:
                amendment = {
                    "id": str(len(ocds_release["tender"].get("amendments", [])) + 1),
                    "rationaleClassifications": [
                        {
                            "id": change_reason_code,
                            "scheme": "eu-change-corrig-justification"
                        }
                    ]
                }
                ocds_release["tender"]["amendments"] = ocds_release["tender"].get("amendments", [])
                ocds_release["tender"]["amendments"].append(amendment)




    # Handle BT-142-LotResult * Winner Chosen
    lot_result_nodes = root.findall(".//efext:EformsExtension/efac:NoticeResult/efac:LotResult", namespaces=namespaces)
    for lot_result_node in lot_result_nodes:
        tender_result_code_node = lot_result_node.find("cbc:TenderResultCode", namespaces=namespaces)
        if tender_result_code_node is not None:
            tender_result_code = tender_result_code_node.text
            tender_lot_node = lot_result_node.find("efac:TenderLot/cbc:ID[@schemeName='Lot']", namespaces=namespaces)
            if tender_lot_node is not None:
                tender_lot_id = tender_lot_node.text
                if tender_result_code == "open-nw":
                    for lot in ocds_release["tender"]["lots"]:
                        if lot["id"] == tender_lot_id:
                            lot["status"] = "active"
                else:
                    lot_result_id_node = lot_result_node.find("cbc:ID", namespaces=namespaces)
                    if lot_result_id_node is not None:
                        lot_result_id = lot_result_id_node.get("{http://www.w3.org/XML/1998/namespace}schemeName")
                        if lot_result_id == "result":
                            award_id = lot_result_id_node.text
                            existing_award = next((award for award in ocds_release.get("awards", []) if award["id"] == award_id), None)
                            if existing_award:
                                if tender_result_code == "selec-w":
                                    existing_award["status"] = "active"
                                    # Look up the code's label in the authority table and map it to the award's .statusDetails
                                elif tender_result_code == "clos-nw":
                                    existing_award["status"] = "unsuccessful"
                                    # Look up the code's label in the authority table and map it to the award's .statusDetails

    # Handle BT-144-LotResult * Not Awarded Reason
    lot_result_nodes = root.findall(".//efext:EformsExtension/efac:NoticeResult/efac:LotResult", namespaces=namespaces)
    for lot_result_node in lot_result_nodes:
        decision_reason_code_node = lot_result_node.find("efac:DecisionReason/efbc:DecisionReasonCode", namespaces=namespaces)
        if decision_reason_code_node is not None:
            decision_reason_code = decision_reason_code_node.text
            lot_result_id_node = lot_result_node.find("cbc:ID", namespaces=namespaces)
            if lot_result_id_node is not None:
                lot_result_id = lot_result_id_node.get("{http://www.w3.org/XML/1998/namespace}schemeName")
                if lot_result_id == "result":
                    award_id = lot_result_id_node.text
                    existing_award = next((award for award in ocds_release.get("awards", []) if award["id"] == award_id), None)
                    if existing_award:
                        existing_award["status"] = "unsuccessful"
                        # Look up the code's label in the authority table and map it to the award's .statusDetails

    return ocds_release

eform_xml = """
<ROOT xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2" xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2" xmlns:efext="urn:edigrampelayo:names:specification:eforms:extensions:eformsext" xmlns:efac="urn:edigrampelayo:names:specification:eforms:aggregatecomponents" xmlns:efbc="urn:edigrampelayo:names:specification:eforms:basiccomponents">
<cac:TenderingTerms>
<cac:ProcurementLegislationDocumentReference>
<cbc:ID schemeName="ELI">http://data.europa.eu/eli/dir/2014/24/oj</cbc:ID>
<cbc:DocumentDescription languageID="ENG">Directive XYZ applies ...</cbc:DocumentDescription>
</cac:ProcurementLegislationDocumentReference>
<cac:ProcurementLegislationDocumentReference>
<cbc:ID>CrossBorderLaw</cbc:ID>
<cbc:DocumentDescription languageID="ENG">Directive XYZ on Cross Border ...</cbc:DocumentDescription>
</cac:ProcurementLegislationDocumentReference>
<cac:ProcurementLegislationDocumentReference>
<cbc:ID>LocalLegalBasis</cbc:ID>
<cbc:DocumentDescription languageID="ENG">National legal basis applies</cbc:DocumentDescription>
</cac:ProcurementLegislationDocumentReference>
</cac:TenderingTerms>
<cbc:RegulatoryDomain>32014L0024</cbc:RegulatoryDomain>
<cbc:NoticeTypeCode listName="competition">cn-standard</cbc:NoticeTypeCode>
<cbc:ContractFolderID>1e86a664-ae3c-41eb-8529-0242ac130003</cbc:ContractFolderID>
<cbc:IssueDate>2019-11-26+01:00</cbc:IssueDate>
<cbc:IssueTime>13:38:54+01:00</cbc:IssueTime>
<cac:ProcurementProjectLot>
<cbc:ID schemeName="Lot">LOT-0001</cbc:ID>
<cac:ProcurementProject>
<cac:ProcurementAdditionalType>
<cbc:ProcurementTypeCode listName="strategic-procurement">inn-pur</cbc:ProcurementTypeCode>
</cac:ProcurementAdditionalType>
</cac:ProcurementProject>
<cac:TenderingProcess>
<cac:FrameworkAgreement>
<cbc:Justification languageID="ENG">The exceptional duration of ...</cbc:Justification>
<cac:SubsequentProcessTenderRequirement>
<cbc:Name>buyer-categories</cbc:Name>
<cbc:Description languageID="ENG">Offices of the "greater region" ...</cbc:Description>
</cac:SubsequentProcessTenderRequirement>
<cbc:MaximumOperatorQuantity>50</cbc:MaximumOperatorQuantity>
</cac:FrameworkAgreement>
<cbc:ProcedureCode listName="procurement-procedure-type">open</cbc:ProcedureCode>
<cac:ProcessJustification>
<cbc:ProcessReasonCode listName="accelerated-procedure">true</cbc:ProcessReasonCode>
</cac:ProcessJustification>
<cbc:GovernmentAgreementConstraintIndicator>true</cbc:GovernmentAgreementConstraintIndicator>
<cac:AwardingTerms>
<cbc:NoFurtherNegotiationIndicator>true</cbc:NoFurtherNegotiationIndicator>
</cac:AwardingTerms>
<cac:AuctionTerms>
<cbc:Description languageID="ENG">The online auction solution ...</cbc:Description>
<cbc:AuctionURI>https://my-online-eauction.eu/</cbc:AuctionURI>
</cac:AuctionTerms>
<cbc:AccessToolsURI>https://my-atypical-tool.com/</cbc:AccessToolsURI>
<cac:NoticeDocumentReference>
<cbc:ID schemeName="notice-id-ref">123e4567-e89b-12d3-a456-426614174000-06</cbc:ID>
<cbc:ReferencedDocumentInternalAddress>PAR-0001</cbc:ReferencedDocumentInternalAddress>
</cac:NoticeDocumentReference>
<cac:AdditionalInformationRequestPeriod>
<cbc:EndDate>2019-11-08+01:00</cbc:EndDate>
<cbc:EndTime>18:00:00+01:00</cbc:EndTime>
</cac:AdditionalInformationRequestPeriod>
<cac:InvitationSubmissionPeriod>
<cbc:StartDate>2019-11-15+01:00</cbc:StartDate>
</cac:InvitationSubmissionPeriod>
<cac:TenderSubmissionDeadlinePeriod>
<cbc:EndDate>2019-11-30+01:00</cbc:EndDate>
<cbc:EndTime>12:00:00+01:00</cbc:EndTime>
</cac:TenderSubmissionDeadlinePeriod>
<cac:ParticipationRequestReceptionPeriod>
<cbc:EndDate>2019-11-25+01:00</cbc:EndDate>
<cbc:EndTime>12:00:00+01:00</cbc:EndTime>
</cac:ParticipationRequestReceptionPeriod>
<cac:OpenTenderEvent>
<cbc:OccurrenceDate>2019-11-05+01:00</cbc:OccurrenceDate>
<cbc:OccurrenceTime>14:00:00+01:00</cbc:OccurrenceTime>
<cac:OccurenceLocation>
<cbc:Description languageID="ENG">online at URL https://event-on-line.org/d22f65 ...</cbc:Description>
</cac:OccurenceLocation>
<cbc:Description languageID="ENG">Any tenderer may attend ...</cbc:Description>
</cac:OpenTenderEvent>
</cac:TenderingProcess>
</cac:ProcurementProjectLot>
<cac:ContractingParty>
<cac:Party>
<cac:PartyIdentification>
<cbc:ID schemeName="organization">ORG-0001</cbc:ID>
</cac:PartyIdentification>
</cac:Party>
<cac:ContractingActivity>
<cbc:ActivityTypeCode listName="authority-activity">gas-oil</cbc:ActivityTypeCode>
</cac:ContractingActivity>
<cac:ContractingPartyType>
<cbc:PartyTypeCode listName="buyer-legal-type">body-pl</cbc:PartyTypeCode>
</cac:ContractingPartyType>
</cac:ContractingParty>
<cbc:PlannedDate>2020-03-15+01:00</cbc:PlannedDate>
<ext:UBLExtensions>
<ext:UBLExtension>
<ext:ExtensionContent>
<efext:EformsExtension>
<efac:NoticeResult>
<efbc:OverallMaximumFrameworkContractsAmount currencyID="EUR">6000</efbc:OverallMaximumFrameworkContractsAmount>
<efac:LotResult>
<efbc:DPSTerminationIndicator>true</efbc:DPSTerminationIndicator>
<efac:TenderLot>
<cbc:ID schemeName="Lot">LOT-0001</cbc:ID>
</efac:TenderLot>
</efac:LotResult>
</efac:NoticeResult>
</efext:EformsExtension>
</ext:ExtensionContent>
</ext:UBLExtension>
</ext:UBLExtensions>
<cac:TenderingProcess>
<cac:ProcessJustification>
<cbc:ProcessReasonCode listName="direct-award-justification">additional</cbc:ProcessReasonCode>
<cbc:ProcessReason languageID="ENG">Direct award is justified ...</cbc:ProcessReason>
<cbc:Description>123e4567-e89b-12d3-a456-426614174000</cbc:Description>
</cac:ProcessJustification>
</cac:TenderingProcess>
<cac:ProcurementProjectLot>
<cbc:ID schemeName="LotsGroup">GLO-0001</cbc:ID>
</cac:ProcurementProjectLot>
<cac:TenderingTerms>
<cac:LotDistribution>
<cac:LotsGroup>
<cbc:LotsGroupID schemeName="LotsGroup">GLO-0001</cbc:LotsGroupID>
<cac:ProcurementProjectLotReference>
<cbc:ID schemeName="Lot">LOT-0002</cbc:ID>
</cac:ProcurementProjectLotReference>
</cac:LotsGroup>
</cac:LotDistribution>
</cac:TenderingTerms>
<cac:ProcurementProjectLot>
<cbc:ID schemeName="Lot">LOT-0003</cbc:ID>
<cac:TenderingTerms>
<cac:CallForTendersDocumentReference>
<cbc:ID>20210521/CTFD/ENG/7654-02</cbc:ID>
<cbc:DocumentType>restricted-document</cbc:DocumentType>
</cac:CallForTendersDocumentReference>
</cac:TenderingTerms>
</cac:ProcurementProjectLot>
<cac:ProcurementProjectLot>
<cbc:ID schemeName="Part">PAR-0000</cbc:ID>
<cac:TenderingTerms>
<cac:CallForTendersDocumentReference>
<cbc:ID>20210521/CTFD/ENG/7654-02</cbc:ID>
<cbc:DocumentType>restricted-document</cbc:DocumentType>
</cac:CallForTendersDocumentReference>
</cac:TenderingTerms>
</cac:ProcurementProjectLot>
<ext:UBLExtensions>
<ext:UBLExtension>
<ext:ExtensionContent>
<efext:EformsExtension>
<efac:Changes>
<efac:Change>
<efac:ChangeReason>
<cbc:ReasonCode listName="change-corrig-justification">update-add</cbc:ReasonCode>
</efac:ChangeReason>
<efbc:ChangeDescription>Some additional information ...</efbc:ChangeDescription>
<efac:ChangedSection>
<efbc:ChangedSectionIdentifier>LOT-0003</efbc:ChangedSectionIdentifier>
</efac:ChangedSection>
</efac:Change>
<efac:Change>
<efac:ChangedSection>
<efbc:ChangedSectionIdentifier>LOT-0004</efbc:ChangedSectionIdentifier>
</efac:ChangedSection>
</efac:Change>
</efac:Changes>
<efac:NoticeResult>
<efac:LotResult>
<cbc:ID schemeName="result">RES-0001</cbc:ID>
<cbc:TenderResultCode listName="winner-selection-status">selec-w</cbc:TenderResultCode>
<efac:TenderLot>
<cbc:ID schemeName="Lot">LOT-0001</cbc:ID>
</efac:TenderLot>
</efac:LotResult>
<efac:LotResult>
<cbc:ID schemeName="result">RES-0002</cbc:ID>
<efac:DecisionReason>
<efbc:DecisionReasonCode listName="non-award-justification">no-rece</efbc:DecisionReasonCode>
</efac:DecisionReason>
<efac:TenderLot>
<cbc:ID schemeName="Lot">LOT-0002</cbc:ID>
</efac:TenderLot>
</efac:LotResult>
</efac:NoticeResult>
<efac:NoticeResult>
<efac:LotTender>
<cbc:ID schemeName="tender">TEN-0001</cbc:ID>
<efac:TenderLot>
<cbc:ID schemeName="Lot">LOT-0001</cbc:ID>
</efac:TenderLot>
</efac:LotTender>
</efac:NoticeResult>
</efext:EformsExtension>
</ext:ExtensionContent>
</ext:UBLExtension>
</ext:UBLExtensions>
</ROOT>
"""


ocds_release = convert_eform_to_ocds(eform_xml) 
print(ocds_release)