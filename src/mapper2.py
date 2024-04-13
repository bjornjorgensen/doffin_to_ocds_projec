from lxml import etree
from dateutil import parser, tz
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
        gpa_coverage_node = lot_node.find("cac:TenderingProcess/cbc:GovernmentAgreementConstraintIndicator", namespaces=namespaces)
        if gpa_coverage_node is not None and gpa_coverage_node.text.lower() == "true":
            for lot in ocds_release["tender"]["lots"]:
                if lot["id"] == lot_id:
                    lot["coveredBy"] = ["GPA"]

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
            "futureNoticeDate": parser.parse(planned_date).isoformat()
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
                            "endDate": parser.parse(combined_datetime).isoformat()
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
                "endDate": parser.parse(combined_datetime).isoformat()
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
                        lot["secondStage"]["invitationDate"] = parser.parse(start_date).isoformat()

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
                            "endDate": parser.parse(combined_datetime).isoformat()
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
                            "endDate": parser.parse(combined_datetime).isoformat()
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
                            "startDate": parser.parse(combined_datetime).isoformat()
                        }
                        lot["bidOpening"] = {
                            "date": parser.parse(combined_datetime).isoformat()
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
                    if change_description:
                        amendment["description"] = change_description
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
                    if change_description:
                        amendment["description"] = change_description
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
                    elif tender_result_code == "clos-nw":
                        existing_award["status"] = "unsuccessful"

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

    # Handle BT-1451-Contract * Winner Decision Date
    for notice_result_node in root.findall(".//efext:EformsExtension/efac:NoticeResult", namespaces=namespaces):
        settled_contract_node = notice_result_node.find("efac:SettledContract", namespaces=namespaces)
        if settled_contract_node is not None:
            award_date_node = settled_contract_node.find("cbc:AwardDate", namespaces=namespaces)
            if award_date_node is not None:
                award_date = award_date_node.text
            contract_id_node = settled_contract_node.find("cbc:ID", namespaces=namespaces)
            if contract_id_node is not None:
                contract_id = contract_id_node.get("{http://www.w3.org/XML/1998/namespace}schemeName")
            if contract_id == "contract":
                contract_id = contract_id_node.text
            for lot_result_node in notice_result_node.findall("efac:LotResult", namespaces=namespaces):
                lot_result_contract_id_node = lot_result_node.find("efac:SettledContract/cbc:ID[@schemeName='contract']", namespaces=namespaces)
                if lot_result_contract_id_node is not None and lot_result_contract_id_node.text == contract_id:
                    lot_result_id_node = lot_result_node.find("cbc:ID", namespaces=namespaces)
                    if lot_result_id_node is not None:
                        lot_result_id = lot_result_id_node.get("{http://www.w3.org/XML/1998/namespace}schemeName")
                    if lot_result_id == "result":
                        award_id = lot_result_id_node.text
                        existing_award = next((award for award in ocds_release.get("awards", []) if award["id"] == award_id), None)
                        if existing_award:
                            if not existing_award.get("date") or parser.parse(award_date).date() < existing_award["date"]:
                                existing_award["date"] = parser.parse(award_date).isoformat()
    # Handle BT-15-Lot * Documents URL
    for lot_node in root.findall(".//cac:ProcurementProjectLot[cbc:ID/@schemeName='Lot']", namespaces=namespaces):
        lot_id = lot_node.find("cbc:ID", namespaces=namespaces).text
        document_reference_nodes = lot_node.findall("cac:TenderingTerms/cac:CallForTendersDocumentReference/cac:Attachment[../cbc:DocumentType/text()='non-restricted-document']", namespaces=namespaces)
        for document_reference_node in document_reference_nodes:
            uri_node = document_reference_node.find("cac:ExternalReference/cbc:URI", namespaces=namespaces)
            if uri_node is not None:
                document_id = document_reference_node.find("../cbc:ID", namespaces=namespaces).text
                existing_document = next((doc for doc in ocds_release["tender"].get("documents", []) if doc["id"] == document_id), None)
                if not existing_document:
                    ocds_release["tender"]["documents"] = ocds_release["tender"].get("documents", [])
                    new_document = {
                        "id": document_id,
                        "documentType": "biddingDocuments",
                        "url": uri_node.text,
                        "relatedLots": [lot_id]
                    }
                    ocds_release["tender"]["documents"].append(new_document)
                else:
                    if "relatedLots" not in existing_document or lot_id not in existing_document["relatedLots"]:
                        existing_document.setdefault("relatedLots", []).append(lot_id)
                    existing_document["url"] = uri_node.text

    # Handle BT-16-Organization-Company Organisation Part Name
    for organization_node in root.findall(".//efext:EformsExtension/efac:Organizations/efac:Organization/efac:Company", namespaces=namespaces):
        organization_id_node = organization_node.find("cac:PartyIdentification/cbc:ID[@schemeName='organization']", namespaces=namespaces)
        if organization_id_node is not None:
            organization_id = organization_id_node.text
            existing_organization = next((party for party in ocds_release["parties"] if party["id"] == organization_id), None)
            if existing_organization:
                department_node = organization_node.find("cac:PostalAddress/cbc:Department", namespaces=namespaces)
                if department_node is not None:
                    existing_organization["name"] += f" - {department_node.text}"

    # Handle BT-16-Organization-TouchPoint Part Name
    for touchpoint_node in root.findall(".//efext:EformsExtension/efac:Organizations/efac:Organization/efac:TouchPoint", namespaces=namespaces):
        touchpoint_id_node = touchpoint_node.find("cac:PartyIdentification/cbc:ID[@schemeName='touchpoint']", namespaces=namespaces)
        if touchpoint_id_node is not None:
            touchpoint_id = touchpoint_id_node.text
            existing_touchpoint = next((party for party in ocds_release["parties"] if party["id"] == touchpoint_id), None)
            if existing_touchpoint:
                department_node = touchpoint_node.find("cac:PostalAddress/cbc:Department", namespaces=namespaces)
                if department_node is not None:
                    existing_touchpoint["name"] += f" - {department_node.text}"
                company_id_node = touchpoint_node.find("../efac:Company/cac:PartyLegalEntity/cbc:CompanyID", namespaces=namespaces)
                if company_id_node is not None:
                    existing_touchpoint["identifier"] = {
                        "id": company_id_node.text,
                        "scheme": "internal"
                    }

    # Handle BT-160-Tender * Concession Revenue Buyer
    for notice_result_node in root.findall(".//efext:EformsExtension/efac:NoticeResult", namespaces=namespaces):
        for lot_tender_node in notice_result_node.findall("efac:LotTender", namespaces=namespaces):
            lot_tender_id = lot_tender_node.find("cbc:ID", namespaces=namespaces).get("{http://www.w3.org/XML/1998/namespace}schemeName")
            if lot_tender_id == "tender":
                lot_tender_id = lot_tender_node.find("cbc:ID", namespaces=namespaces).text
                concession_revenue_node = lot_tender_node.find("efac:ConcessionRevenue", namespaces=namespaces)
                if concession_revenue_node is not None:
                    revenue_buyer_amount_node = concession_revenue_node.find("efbc:RevenueBuyerAmount", namespaces=namespaces)
                    if revenue_buyer_amount_node is not None:
                        settled_contract_id_node = notice_result_node.find(f"efac:SettledContract[efac:LotTender/cbc:ID[@schemeName='tender']/text()='{lot_tender_id}']/cbc:ID", namespaces=namespaces)
                        if settled_contract_id_node is not None:
                            settled_contract_id = settled_contract_id_node.text
                            existing_contract = next((contract for contract in ocds_release.get("contracts", []) if contract["id"] == settled_contract_id), None)
                            if existing_contract:
                                existing_contract["value"] = {
                                    "amount": float(revenue_buyer_amount_node.text),  # Assuming the text is the amount
                                    "currency": revenue_buyer_amount_node.get("{http://www.w3.org/XML/1998/namespace}currencyID")  # Extract currency if available
                                }
                                # Update the implementation status if needed
                                existing_contract["status"] = "active"  # Assuming that having a revenue implies the contract is active

    # Handle BT-170-Procedure * Duration
    for procedure_node in root.findall(".//efext:EformsExtension/efac:Procedure", namespaces=namespaces):
        duration_node = procedure_node.find("cbc:DurationMeasure", namespaces=namespaces)
        if duration_node is not None:
            duration = duration_node.text  # Duration value
            duration_unit = duration_node.get("unitCode")  # Duration unit, e.g., DAY, MONTH
            ocds_release["tender"]["tenderPeriod"] = ocds_release["tender"].get("tenderPeriod", {})
            ocds_release["tender"]["tenderPeriod"]["duration"] = duration
            ocds_release["tender"]["tenderPeriod"]["durationUnit"] = duration_unit

    # Handle BT-180-Contract * Framework Agreement
    for contract_node in root.findall(".//cac:Contract", namespaces=namespaces):
        framework_agreement_node = contract_node.find("cac:FrameworkAgreement", namespaces=namespaces)
        if framework_agreement_node is not None:
            contract_id_node = contract_node.find("cbc:ID", namespaces=namespaces)
            contract_id = contract_id_node.text if contract_id_node else None
            existing_contract = next((contract for contract in ocds_release.get("contracts", []) if contract["id"] == contract_id), None)
            if existing_contract:
                existing_contract["isFrameworkAgreement"] = True  # Mark the contract as part of a framework agreement



    # Handle BT-162-Tender * Concession Revenue User
    for notice_result_node in root.findall(".//efext:EformsExtension/efac:NoticeResult", namespaces=namespaces):
        for lot_tender_node in notice_result_node.findall("efac:LotTender", namespaces=namespaces):
            lot_tender_id = lot_tender_node.find("cbc:ID", namespaces=namespaces).get("{http://www.w3.org/XML/1998/namespace}schemeName")
            if lot_tender_id == "tender":
                lot_tender_id = lot_tender_node.find("cbc:ID", namespaces=namespaces).text
                concession_revenue_node = lot_tender_node.find("efac:ConcessionRevenue", namespaces=namespaces)
                if concession_revenue_node is not None:
                    revenue_user_amount_node = concession_revenue_node.find("efbc:RevenueUserAmount", namespaces=namespaces)
                    if revenue_user_amount_node is not None:
                        settled_contract_id_node = notice_result_node.find("efac:SettledContract[efac:LotTender/cbc:ID[@schemeName='tender']/text()='" + lot_tender_id + "']/cbc:ID", namespaces=namespaces)
                        if settled_contract_id_node is not None:
                            settled_contract_id = settled_contract_id_node.get("{http://www.w3.org/XML/1998/namespace}schemeName")
                            if settled_contract_id == "contract":
                                settled_contract_id = settled_contract_id_node.text
                                existing_contract = next((contract for contract in ocds_release.get("contracts", []) if contract["id"] == settled_contract_id), None)
                                if existing_contract:
                                    existing_contract["implementation"] = existing_contract.get("implementation", {})
                                    existing_contract["implementation"]["charges"] = existing_contract["implementation"].get("charges", [])
                                    new_charge = {
                                        "id": "user",
                                        "title": "he estimated revenue coming from the users of the concession (e.g. fees and fines).",
                                        "estimatedValue": {
                                            "amount": float(revenue_user_amount_node.text),
                                            "currency": revenue_user_amount_node.get("currencyID")
                                        },
                                        "paidBy": "user"
                                    }
                                    existing_contract["implementation"]["charges"].append(new_charge)

    # Handle BT-163-Tender * Concession Value Description
    for notice_result_node in root.findall(".//efext:EformsExtension/efac:NoticeResult", namespaces=namespaces):
        for lot_tender_node in notice_result_node.findall("efac:LotTender", namespaces=namespaces):
            lot_tender_id = lot_tender_node.find("cbc:ID", namespaces=namespaces).get("{http://www.w3.org/XML/1998/namespace}schemeName")
            if lot_tender_id == "tender":
                lot_tender_id = lot_tender_node.find("cbc:ID", namespaces=namespaces).text
                concession_revenue_node = lot_tender_node.find("efac:ConcessionRevenue", namespaces=namespaces)
                if concession_revenue_node is not None:
                    value_description_node = concession_revenue_node.find("efbc:ValueDescription", namespaces=namespaces)
                    if value_description_node is not None:
                        value_description = value_description_node.text
                        lot_result_node = notice_result_node.find("efac:LotResult[efac:LotTender/cbc:ID[@schemeName='tender']/text()='" + lot_tender_id + "']", namespaces=namespaces)
                        if lot_result_node is not None:
                            lot_result_id_node = lot_result_node.find("cbc:ID", namespaces=namespaces)
                            if lot_result_id_node is not None:
                                lot_result_id = lot_result_id_node.get("{http://www.w3.org/XML/1998/namespace}schemeName")
                                if lot_result_id == "result":
                                    award_id = lot_result_id_node.text
                                    existing_award = next((award for award in ocds_release.get("awards", []) if award["id"] == award_id), None)
                                    if not existing_award:
                                        ocds_release["awards"] = ocds_release.get("awards", [])
                                        new_award = {
                                            "id": award_id,
                                            "valueCalculationMethod": value_description
                                        }
                                        tender_lot_node = lot_result_node.find("efac:TenderLot/cbc:ID[@schemeName='Lot']", namespaces=namespaces)
                                        if tender_lot_node is not None:
                                            new_award["relatedLots"] = [tender_lot_node.text]
                                        ocds_release["awards"].append(new_award)
                                    else:
                                        existing_award["valueCalculationMethod"] = value_description

    # Handle BT-165-Organization-Company Winner Size
    for organization_node in root.findall(".//efext:EformsExtension/efac:Organizations/efac:Organization/efac:Company", namespaces=namespaces):
        organization_id_node = organization_node.find("cac:PartyIdentification/cbc:ID[@schemeName='organization']", namespaces=namespaces)
        if organization_id_node is not None:
            organization_id = organization_id_node.text
            existing_organization = next((party for party in ocds_release["parties"] if party["id"] == organization_id), None)
            if existing_organization:
                company_size_code_node = organization_node.find("efbc:CompanySizeCode", namespaces=namespaces)
                if company_size_code_node is not None:
                    existing_organization["details"] = existing_organization.get("details", {})
                    existing_organization["details"]["scale"] = company_size_code_node.text

    # Handle BT-17-Lot * SubmissionElectronic
    for lot_node in root.findall(".//cac:ProcurementProjectLot[cbc:ID/@schemeName='Lot']", namespaces=namespaces):
        lot_id = lot_node.find("cbc:ID", namespaces=namespaces).text
        submission_method_code_node = lot_node.find("cac:TenderingProcess/cbc:SubmissionMethodCode[@listName='esubmission']", namespaces=namespaces)
        if submission_method_code_node is not None:
            submission_method_code = submission_method_code_node.text
            for lot in ocds_release["tender"]["lots"]:
                if lot["id"] == lot_id:
                    lot["submissionTerms"] = lot.get("submissionTerms", {})
                    lot["submissionTerms"]["electronicSubmissionPolicy"] = submission_method_code

    # Handle BT-18-Lot * Submission URL
    for lot_node in root.findall(".//cac:ProcurementProjectLot[cbc:ID/@schemeName='Lot']", namespaces=namespaces):
        lot_id = lot_node.find("cbc:ID", namespaces=namespaces).text
        endpoint_id_node = lot_node.find("cac:TenderingTerms/cac:TenderRecipientParty/cbc:EndpointID", namespaces=namespaces)
        if endpoint_id_node is not None:
            endpoint_id = endpoint_id_node.text
            for lot in ocds_release["tender"]["lots"]:
                if lot["id"] == lot_id:
                    lot["submissionMethodDetails"] = endpoint_id

    # Handle BT-19-Lot * Submission Nonelectronic Justification
    for lot_node in root.findall(".//cac:ProcurementProjectLot[cbc:ID/@schemeName='Lot']", namespaces=namespaces):
        lot_id = lot_node.find("cbc:ID", namespaces=namespaces).text
        process_justification_node = lot_node.find("cac:TenderingProcess/cac:ProcessJustification[cbc:ProcessReasonCode/@listName='no-esubmission-justification']/cbc:ProcessReasonCode", namespaces=namespaces)
        if process_justification_node is not None:
            process_reason_code = process_justification_node.text
            # Look up the code's label in the authority table and map it to the lot's .submissionTerms.nonElectronicSubmissionRationale
            for lot in ocds_release["tender"]["lots"]:
                if lot["id"] == lot_id:
                    lot["submissionTerms"] = lot.get("submissionTerms", {})
                    lot["submissionTerms"]["nonElectronicSubmissionRationale"] = process_reason_code  # Replace with actual label lookup

    # Handle BT-191-Tender Country Origin
    for notice_result_node in root.findall(".//efext:EformsExtension/efac:NoticeResult", namespaces=namespaces):
        for lot_tender_node in notice_result_node.findall("efac:LotTender", namespaces=namespaces):
            lot_tender_id = lot_tender_node.find("cbc:ID", namespaces=namespaces).get("{http://www.w3.org/XML/1998/namespace}schemeName")
            if lot_tender_id == "tender":
                lot_tender_id = lot_tender_node.find("cbc:ID", namespaces=namespaces).text
                origin_node = lot_tender_node.find("efac:Origin", namespaces=namespaces)
                if origin_node is not None:
                    area_code_node = origin_node.find("efbc:AreaCode", namespaces=namespaces)
                    if area_code_node is not None:
                        area_code = area_code_node.text
                        if area_code == "1A0":  # Kosovo
                            country_code = "XK"
                        else:
                            # Look up the equivalent ISO 3166-1 alpha-2 code in the authority table
                            country_code = area_code  # Replace with actual lookup
                        existing_bid = next((bid for bid in ocds_release.get("bids", {}).get("details", []) if bid["id"] == lot_tender_id), None)
                        if existing_bid:
                            existing_bid["countriesOfOrigin"] = existing_bid.get("countriesOfOrigin", [])
                            if country_code not in existing_bid["countriesOfOrigin"]:
                                existing_bid["countriesOfOrigin"].append(country_code)
                        else:
                            ocds_release["bids"] = ocds_release.get("bids", {"details": []})
                            new_bid = {
                                "id": lot_tender_id,
                                "countriesOfOrigin": [country_code]
                            }
                            tender_lot_node = lot_tender_node.find("efac:TenderLot/cbc:ID[@schemeName='Lot']", namespaces=namespaces)
                            if tender_lot_node is not None:
                                new_bid["relatedLots"] = [tender_lot_node.text]
                            ocds_release["bids"]["details"].append(new_bid)

    # Handle BT-193-Tender Tender Variant
    for notice_result_node in root.findall(".//efext:EformsExtension/efac:NoticeResult", namespaces=namespaces):
        for lot_tender_node in notice_result_node.findall("efac:LotTender", namespaces=namespaces):
            lot_tender_id = lot_tender_node.find("cbc:ID", namespaces=namespaces).get("{http://www.w3.org/XML/1998/namespace}schemeName")
            if lot_tender_id == "tender":
                lot_tender_id = lot_tender_node.find("cbc:ID", namespaces=namespaces).text
                tender_variant_indicator_node = lot_tender_node.find("efbc:TenderVariantIndicator", namespaces=namespaces)
                if tender_variant_indicator_node is not None and tender_variant_indicator_node.text.lower() == "true":
                    existing_bid = next((bid for bid in ocds_release.get("bids", {}).get("details", []) if bid["id"] == lot_tender_id), None)
                    if existing_bid:
                        existing_bid["variant"] = True
                    else:
                        ocds_release["bids"] = ocds_release.get("bids", {"details": []})
                        new_bid = {
                            "id": lot_tender_id,
                            "variant": True
                        }
                        tender_lot_node = lot_tender_node.find("efac:TenderLot/cbc:ID[@schemeName='Lot']", namespaces=namespaces)
                        if tender_lot_node is not None:
                            new_bid["relatedLots"] = [tender_lot_node.text]
                        ocds_release["bids"]["details"].append(new_bid)

    # Handle BT-171-Tender Tender Rank
    for notice_result_node in root.findall(".//efext:EformsExtension/efac:NoticeResult", namespaces=namespaces):
        for lot_tender_node in notice_result_node.findall("efac:LotTender", namespaces=namespaces):
            lot_tender_id = lot_tender_node.find("cbc:ID", namespaces=namespaces).get("{http://www.w3.org/XML/1998/namespace}schemeName")
            if lot_tender_id == "tender":
                lot_tender_id = lot_tender_node.find("cbc:ID", namespaces=namespaces).text
                rank_code_node = lot_tender_node.find("cbc:RankCode", namespaces=namespaces)
                if rank_code_node is not None:
                    rank_code = rank_code_node.text
                    existing_bid = next((bid for bid in ocds_release.get("bids", {}).get("details", []) if bid["id"] == lot_tender_id), None)
                    if existing_bid:
                        existing_bid["rank"] = int(rank_code)
                    else:
                        ocds_release["bids"] = ocds_release.get("bids", {"details": []})
                        new_bid = {
                            "id": lot_tender_id,
                            "rank": int(rank_code)
                        }
                        tender_lot_node = lot_tender_node.find("efac:TenderLot/cbc:ID[@schemeName='Lot']", namespaces=namespaces)
                        if tender_lot_node is not None:
                            new_bid["relatedLots"] = [tender_lot_node.text]
                        ocds_release["bids"]["details"].append(new_bid)


    # Handle BT-195(BT-541)-LotsGroup-Weight Unpublished Identifier
    for lot_node in root.findall(".//cac:ProcurementProjectLot[cbc:ID/@schemeName='LotsGroup']", namespaces=namespaces):
        lot_id = lot_node.find("cbc:ID", namespaces=namespaces).text
        for awarding_criterion_node in lot_node.findall("cac:TenderingTerms/cac:AwardingTerms/cac:AwardingCriterion/cac:SubordinateAwardingCriterion", namespaces=namespaces):
            for parameter_node in awarding_criterion_node.findall("ext:UBLExtensions/ext:UBLExtension/ext:ExtensionContent/efext:EformsExtension/efac:AwardCriterionParameter[efbc:ParameterCode/@listName='number-weight']/efac:FieldsPrivacy/efbc:FieldIdentifierCode", namespaces=namespaces):
                field_identifier = parameter_node.text
                withheld_information_item = {
                    "field": "awa-cri-num",
                    "id": f"awa-cri-num-weight-{lot_id}",
                    "name": "Award Criterion Number Weight"
                }
                ocds_release.setdefault("withheldInformation", []).append(withheld_information_item)

    return ocds_release


#ocds_release = convert_eform_to_ocds(eform_xml)
#print(json.dumps(ocds_release, indent=2))




