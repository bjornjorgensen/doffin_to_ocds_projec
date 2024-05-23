import logging
import uuid
import json
from lxml import etree
from datetime import datetime
import dateutil.parser

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

def parse_iso_date(date_str):
    try:
        return dateutil.parser.isoparse(date_str)
    except ValueError as e:
        logging.error(f'Error parsing date: {date_str} - {e}')
        return None
    
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
        namespaces = namespaces or self.nsmap
        try:
            nodes = element.xpath(xpath, namespaces=namespaces)
            return nodes[0].text if nodes else None
        except etree.XPathEvalError as e:
            logging.error(f"Invalid XPath expression: {xpath} - {e}")
            return None

    def find_attribute(self, element, xpath, attribute, default=None):
        if xpath.startswith("//"):
            xpath = ".\\" + xpath
        node = element.find(xpath, namespaces=self.nsmap)
        return node.get(attribute) if node is not None else default
    
    def find_node(self, element, xpath, namespaces=None):
        node = element.find(xpath, namespaces=namespaces if namespaces else self.nsmap)
        return node

    def find_nodes(self, element, xpath, namespaces=None):
        return element.findall(xpath, namespaces=namespaces if namespaces else self.nsmap)

class TEDtoOCDSConverter:
    def __init__(self, parser):
        self.parser = parser
        self.form_type_mapping = {
            'planning': {'tag': ['tender'], 'tender_status': 'planned'},
            'competition': {'tag': ['tender'], 'tender_status': 'active'},
            'change': {'tag': ['tenderUpdate'], 'tender_status': None},
            'result': {'tag': ['award', 'contract'], 'tender_status': 'complete'},
            'dir-awa-pre': {'tag': ['award', 'contract'], 'tender_status': 'complete'},
            'cont-modif': {'tag': ['awardUpdate', 'contractUpdate'], 'tender_status': None}
        }
        self.awards = []
        self.parties = []
        self.tender = {
            "lots": [],
            "bids": {
                "statistics": []
            },
            "lotGroups": []
        }
        self.budget_finances = []
        logging.info('TEDtoOCDSConverter initialized with mapping.')

    def fetch_bt710_bt711_bid_statistics(self, root_element):
        notice_results = root_element.xpath(".//efac:NoticeResult", namespaces=self.parser.nsmap)
        stat_id = 1

        for notice_result in notice_results:
            lot_results = notice_result.xpath(".//efac:LotResult", namespaces=self.parser.nsmap)
            for lot_result in lot_results:
                lot_id = self.parser.find_text(lot_result, "./efac:TenderLot/cbc:ID", namespaces=self.parser.nsmap)

                lower_tender_amount = self.parser.find_text(lot_result, "./cbc:LowerTenderAmount", namespaces=self.parser.nsmap)
                lower_tender_currency = self.parser.find_attribute(lot_result, "./cbc:LowerTenderAmount", "currencyID")
                if lower_tender_amount and lower_tender_currency:
                    self.tender["bids"]["statistics"].append({
                        "id": str(stat_id),
                        "measure": "lowestValidBidValue",
                        "value": float(lower_tender_amount),
                        "currency": lower_tender_currency,
                        "relatedLot": lot_id
                    })
                    stat_id += 1

                higher_tender_amount = self.parser.find_text(lot_result, "./cbc:HigherTenderAmount", namespaces=self.parser.nsmap)
                higher_tender_currency = self.parser.find_attribute(lot_result, "./cbc:HigherTenderAmount", "currencyID")
                if higher_tender_amount and higher_tender_currency:
                    self.tender["bids"]["statistics"].append({
                        "id": str(stat_id),
                        "measure": "highestValidBidValue",
                        "value": float(higher_tender_amount),
                        "currency": higher_tender_currency,
                        "relatedLot": lot_id
                    })
                    stat_id += 1

    def fetch_bt09_cross_border_law(self, root_element):
        cross_border_docs = root_element.xpath(".//cac:TenderingTerms/cac:ProcurementLegislationDocumentReference[cbc:ID='CrossBorderLaw']", namespaces=self.parser.nsmap)
        for doc in cross_border_docs:
            law_description = self.parser.find_text(doc, "./cbc:DocumentDescription", namespaces=self.parser.nsmap)
            if law_description:
                self.tender["crossBorderLaw"] = law_description

    def fetch_bt111_lot_buyer_categories(self, root_element):
        lots = root_element.xpath(".//cac:ProcurementProjectLot[cbc:ID/@schemeName='Lot']", namespaces=self.parser.nsmap)
        for lot in lots:
            lot_id = self.parser.find_text(lot, "./cbc:ID", namespaces=self.parser.nsmap)
            subsequent_req = lot.xpath(".//cac:FrameworkAgreement/cac:SubsequentProcessTenderRequirement[cbc:Name='buyer-categories']/cbc:Description", namespaces=self.parser.nsmap)
            description = subsequent_req[0].text if subsequent_req else None
            if description:
                for lot_info in self.tender.get("lots", []):
                    if lot_info["id"] == lot_id:
                        lot_info.setdefault("techniques", {}).setdefault("frameworkAgreement", {})["buyerCategories"] = description

    def fetch_bt766_dynamic_purchasing_system_lot(self, root_element):
        lots = root_element.xpath(".//cac:ProcurementProjectLot[cbc:ID/@schemeName='Lot']", namespaces=self.parser.nsmap)
        for lot in lots:
            lot_id = self.parser.find_text(lot, "./cbc:ID", namespaces=self.parser.nsmap)
            dps_code = self.parser.find_text(lot, "./cac:TenderingProcess/cac:ContractingSystem/cbc:ContractingSystemTypeCode[@listName='dps-usage']", namespaces=self.parser.nsmap)
            if dps_code and dps_code.lower() != "none":
                lot_info = {
                    "id": lot_id,
                    "techniques": {
                        "hasDynamicPurchasingSystem": True,
                        "dynamicPurchasingSystem": {
                            "type": self.map_dps_code(dps_code)
                        }
                    }
                }
                self.add_or_update_lot(self.tender["lots"], lot_info)

    def map_dps_code(self, code):
        mapping = {
            "dps-nlist": "closed",
            "dps-openall": "open",
        }
        return mapping.get(code, code)
    
    def fetch_bt766_dynamic_purchasing_system_part(self, root_element):
        parts = root_element.xpath(".//cac:ProcurementProjectLot[cbc:ID/@schemeName='Part']", namespaces=self.parser.nsmap)
        for part in parts:
            dps_code = self.parser.find_text(part, "./cac:TenderingProcess/cac:ContractingSystem/cbc:ContractingSystemTypeCode[@listName='dps-usage']", namespaces=self.parser.nsmap)
            if dps_code and dps_code.lower() != "none":
                self.tender.setdefault("techniques", {}).update({
                    "hasDynamicPurchasingSystem": True,
                    "dynamicPurchasingSystem": {
                        "type": self.map_dps_code(dps_code)
                    }
                })

    def fetch_opt_300_contract_signatory(self, root_element):
        signatories = root_element.xpath(".//efext:EformsExtension/efac:NoticeResult/efac:SettledContract/cac:SignatoryParty/cac:PartyIdentification/cbc:ID", namespaces=self.parser.nsmap)
        for signatory in signatories:
            signatory_id = signatory.text
            if signatory_id:
                contract_id = signatory.xpath("ancestor::efext:EformsExtension/efac:NoticeResult/efac:SettledContract/cbc:ID", namespaces=self.parser.nsmap)[0].text
                self.add_or_update_party(self.parties, {
                    "id": signatory_id,
                    "roles": ["buyer"],
                })
                org_name = self.parser.find_text(root_element, f".//efac:Organization/efac:Company[cac:PartyIdentification/cbc:ID='{signatory_id}']/cac:PartyName/cbc:Name", namespaces=self.parser.nsmap)
                if org_name:
                    self.add_or_update_party(self.parties, {
                        "id": signatory_id,
                        "name": org_name,
                    })
                for award in self.awards:
                    if award["id"] == contract_id:
                        award.setdefault("buyers", []).append({"id": signatory_id})                                                           

    def fetch_bt712_complaints_statistics(self, root_element):
        notice_results = root_element.xpath(".//efac:NoticeResult", namespaces=self.parser.nsmap)
        stat_id = len(self.tender["bids"]["statistics"]) + 1

        for notice_result in notice_results:
            lot_results = notice_result.xpath(".//efac:LotResult", namespaces=self.parser.nsmap)
            for lot_result in lot_results:
                lot_id = self.parser.find_text(lot_result, "./efac:TenderLot/cbc:ID", namespaces=self.parser.nsmap)

                appeal_stats = lot_result.xpath(".//efac:AppealRequestsStatistics", namespaces=self.parser.nsmap)
                for stats in appeal_stats:
                    stats_code = self.parser.find_text(stats, "./efbc:StatisticsCode", namespaces=self.parser.nsmap)
                    stats_number = self.parser.find_text(stats, "./efbc:StatisticsNumeric", namespaces=self.parser.nsmap)

                    if stats_code == "complainants" and stats_number:
                        self.tender["bids"]["statistics"].append({
                            "id": str(stat_id),
                            "measure": "complainants",
                            "value": int(stats_number),
                            "relatedLot": lot_id
                        })
                        stat_id += 1


    def fetch_bt31_max_lots_submitted(self, root_element):
        """
        Fetches BT-31: The maximum number of lots for which one tenderer can submit tenders
        and maps to tender.lotDetails.maximumLotsBidPerSupplier.
        """
        max_lots_submitted = self.parser.find_text(root_element, ".//cac:TenderingTerms/cac:LotDistribution/cbc:MaximumLotsSubmittedNumeric", namespaces=self.parser.nsmap)
        if max_lots_submitted:
            self.tender.setdefault('lotDetails', {})['maximumLotsBidPerSupplier'] = int(max_lots_submitted)
            logging.info(f"Extracted Maximum Lots Submitted: {max_lots_submitted}")
        else:
            logging.warning("Maximum Lots Submitted information not found.")

    def fetch_bt33_max_lots_awarded(self, root_element):
        """
        Fetches BT-33: The maximum number of lots for which contract(s) can be awarded to one tenderer
        and maps to tender.lotDetails.maximumLotsAwardedPerSupplier.
        """
        max_lots_awarded = self.parser.find_text(root_element, ".//cac:TenderingTerms/cac:LotDistribution/cbc:MaximumLotsAwardedNumeric", namespaces=self.parser.nsmap)
        if max_lots_awarded:
            self.tender.setdefault('lotDetails', {})['maximumLotsAwardedPerSupplier'] = int(max_lots_awarded)
            logging.info(f"Extracted Maximum Lots Awarded: {max_lots_awarded}")
        else:
            logging.warning("Maximum Lots Awarded information not found.")

    def fetch_bt763_lots_all_required(self, root_element):
        """
        Fetches BT-763: The tenderer must submit tenders for all lots.
        and sets tender.lotDetails.maximumLotsBidPerSupplier to float('inf') if value is 'all'.
        """
        part_presentation_code = self.parser.find_text(root_element, ".//cac:TenderingProcess/cbc:PartPresentationCode[@listName='tenderlot-presentation']", namespaces=self.parser.nsmap)
        if part_presentation_code == 'all':
            self.tender.setdefault('lotDetails', {})['maximumLotsBidPerSupplier'] = float('inf')
            logging.info("Set Maximum Lots Bid Per Supplier to all lots (infinity).")
        else:
            logging.warning("Part Presentation Code indicating all lots not found.")

    def fetch_bt5010_lot_financing(self, root_element):
        """
        Fetches BT-5010: An identifier of the Union programme used to at least partially
        finance the contract.
        """
        lots = root_element.findall(".//cac:ProcurementProjectLot", namespaces=self.parser.nsmap)
        for lot in lots:
            lot_id = self.parser.find_text(lot, "./cbc:ID", namespaces=self.parser.nsmap)
            financings = lot.findall(".//efac:Funding/efbc:FinancingIdentifier", namespaces=self.parser.nsmap)
            for financing in financings:
                financing_id = financing.text
                self.update_eu_funder(financing_id, lot_id)

    
    def fetch_bt5011_contract_financing(self, root_element):
        """
        Fetches BT-5011: An identifier of the Union programme used to at least partially
        finance the contract.
        """
        contracts = root_element.findall(".//efac:SettledContract", namespaces=self.parser.nsmap)
        for contract in contracts:
            contract_id = self.parser.find_text(contract, "./cbc:ID", namespaces=self.parser.nsmap)
            financings = contract.findall(".//efac:Funding/efbc:FinancingIdentifier", namespaces=self.parser.nsmap)
            for financing in financings:
                financing_id = financing.text
                self.update_eu_funder(financing_id, contract_id, level='contract')

    def fetch_bt60_lot_funding(self, root_element):
        """
        Fetches BT-60: The procurement is at least partially financed by Union funds.
        """
        lots = root_element.findall(".//cac:ProcurementProjectLot", namespaces=self.parser.nsmap)
        for lot in lots:
            funding_program_code = self.parser.find_text(lot, ".//cbc:FundingProgramCode[@listName='eu-funded']", namespaces=self.parser.nsmap)
            if funding_program_code:
                self.update_eu_funder('EU-funds')

    def fetch_opt_301_lotresult_financing(self, root_element):
        """
        Fetches OPT-301: Financing Party (ID reference) for LotResult.
        """
        lot_results = root_element.findall(".//efac:LotResult", namespaces=self.parser.nsmap)
        for lot_result in lot_results:
            financing_party_id = self.parser.find_text(lot_result, ".//cac:FinancingParty/cac:PartyIdentification/cbc:ID", namespaces=self.parser.nsmap)
            if financing_party_id:
                self.update_funder_role(financing_party_id)

    def update_eu_funder(self, financing_id=None, related_id=None, level='lot'):
        """
        Updates the EU funder finance information.
        :param financing_id: Financing Identifier
        :param related_id: Related Lot or Contract ID
        :param level: Specifies if the level is 'lot' or 'contract'
        """
        eu_funder = next((p for p in self.parties if p.get('name') == 'European Union'), None)  # Use .get('name')
        if not eu_funder:
            eu_funder = {
                "id": str(uuid.uuid4()),
                "name": 'European Union',
                "roles": ['funder']
            }
            self.parties.append(eu_funder)
        
        if level == 'lot' and related_id:
            self.budget_finances.append({
                "id": financing_id or 'EU-funded',
                "relatedLots": [related_id],
                "financingParty": {
                    "id": eu_funder["id"],
                    "name": eu_funder["name"]
                }
            })
        elif level == 'contract' and related_id:
            for award in self.awards:
                if award["id"] == related_id:
                    if "finance" not in award:
                        award["finance"] = []
                    award["finance"].append({
                        "id": financing_id or 'EU-funded',
                        "financingParty": {
                            "id": eu_funder["id"],
                            "name": eu_funder["name"]
                        }
                    })
                    break
        else:
            for award in self.awards:
                if related_id in award.get("relatedLots", []):
                    if "finance" not in award:
                        award["finance"] = []
                    award["finance"].append({
                        "id": financing_id or 'EU-funded',
                            "financingParty": {
                                "id": eu_funder["id"],
                                "name": eu_funder["name"]
                            }
                        })

    def update_funder_role(self, funding_party_id):
        """
        Updates the role of the funding party to 'funder', if not already set.
        :param funding_party_id: ID of the financing party
        """
        funder = self.get_or_create_organization(self.parties, funding_party_id)
        if "funder" not in funder["roles"]:
            funder["roles"].append("funder")

    def fetch_bt3202_to_ocds(self, root_element):
        # Ensure the 'bids' dictionary and 'details' list are initialized
        if 'bids' not in self.tender:
            self.tender['bids'] = {}
        if 'details' not in self.tender['bids']:
            self.tender['bids']['details'] = []

        notice_results = root_element.xpath(".//efac:NoticeResult", namespaces=self.parser.nsmap)
        
        for notice_result in notice_results:
            lot_tenders = self.parser.find_nodes(notice_result, ".//efac:LotTender")
            for lot_tender in lot_tenders:
                tender_id = self.parser.find_text(lot_tender, "cbc:ID")
                lot_id = self.parser.find_text(lot_tender, "efac:TenderLot/cbc:ID")
                
                bid = next((bid for bid in self.tender["bids"]["details"] if bid["id"] == tender_id), None)
                if not bid:
                    bid = {
                        "id": tender_id,
                        "relatedLots": [lot_id]
                    }
                    self.tender["bids"]["details"].append(bid)
                else:
                    if "relatedLots" not in bid:
                        bid["relatedLots"] = []
                    if lot_id not in bid["relatedLots"]:
                        bid["relatedLots"].append(lot_id)
                
                rank_code = self.parser.find_text(lot_tender, "cbc:RankCode")
                if rank_code:
                    bid["rank"] = int(rank_code)
                
                tender_ranked_indicator = self.parser.find_text(lot_tender, "efbc:TenderRankedIndicator")
                if tender_ranked_indicator:
                    bid["hasRank"] = tender_ranked_indicator.lower() == 'true'
                    
                origins = self.parser.find_nodes(lot_tender, "efac:Origin/efbc:AreaCode")
                if origins:
                    bid["countriesOfOrigin"] = []
                    for origin in origins:
                        country_code = origin.text
                        iso_country_code = self.convert_language_code(country_code, code_type='country')
                        if iso_country_code and iso_country_code not in bid["countriesOfOrigin"]:
                            bid["countriesOfOrigin"].append(iso_country_code)
                
                tender_variant_indicator = self.parser.find_text(lot_tender, "efbc:TenderVariantIndicator")
                if tender_variant_indicator:
                    bid["variant"] = tender_variant_indicator.lower() == 'true'
                
                tender_reference = self.parser.find_text(lot_tender, "efac:TenderReference/cbc:ID")
                if tender_reference:
                    bid.setdefault("identifiers", []).append({
                        "id": tender_reference,
                        "scheme": "{}-TENDERNL".format(tender_reference.split('/')[0][:2])
                    })
                
                sub_contracting_amount = self.parser.find_text(lot_tender, "efac:SubcontractingTerm/efbc:TermAmount")
                currency_id = self.parser.find_attribute(lot_tender, "efac:SubcontractingTerm/efbc:TermAmount", "currencyID")
                if sub_contracting_amount and currency_id:
                    bid.setdefault("subcontracting", {})["value"] = {
                        "amount": float(sub_contracting_amount),
                        "currency": currency_id
                    }
                
                sub_contracting_desc = self.parser.find_text(lot_tender, "efac:SubcontractingTerm/efbc:TermDescription")
                if sub_contracting_desc:
                    bid.setdefault("subcontracting", {})["description"] = sub_contracting_desc
                
                sub_contracting_percent = self.parser.find_text(lot_tender, "efac:SubcontractingTerm/efbc:TermPercent")
                if sub_contracting_percent:
                    percentage = float(sub_contracting_percent) / 100
                    bid.setdefault("subcontracting", {})["minimumPercentage"] = percentage
                    bid.setdefault("subcontracting", {})["maximumPercentage"] = percentage
                
                sub_contracting_code = self.parser.find_text(lot_tender, "efac:SubcontractingTerm/efbc:TermCode")
                if sub_contracting_code:
                    bid["hasSubcontracting"] = sub_contracting_code.lower() == 'yes'
                
                legal_monetary_total = self.parser.find_text(lot_tender, "cac:LegalMonetaryTotal/cbc:PayableAmount")
                currency_id = self.parser.find_attribute(lot_tender, "cac:LegalMonetaryTotal/cbc:PayableAmount", "currencyID")
                if legal_monetary_total and currency_id:
                    tender_value = {
                        "amount": float(legal_monetary_total),
                        "currency": currency_id
                    }
                    bid["value"] = tender_value


    def fetch_bt500_organization_names(self, root_element):
        """
        Fetch names of organizations (BT-500) and update the organization part names (BT-16).
        """

        # BT-500-Organization-Company
        companies = root_element.findall(".//efac:Organization/efac:Company", namespaces=self.parser.nsmap)
        for company in companies:
            org_id = self.parser.find_text(company, "./cac:PartyIdentification/cbc:ID[@schemeName='organization']")
            if org_id:
                organization = self.get_or_create_organization(self.parties, org_id)
                org_name = self.parser.find_text(company, "./cac:PartyName/cbc:Name")
                department = self.parser.find_text(company, "./cac:PostalAddress/cbc:Department")
                organization['name'] = f"{org_name} - {department}" if department else org_name

        # BT-500-Organization-TouchPoint
        touchpoints = root_element.findall(".//efac:Organization/efac:TouchPoint", namespaces=self.parser.nsmap)
        for touchpoint in touchpoints:
            org_id = self.parser.find_text(touchpoint, "./cac:PartyIdentification/cbc:ID[@schemeName='touchpoint']")
            if org_id:
                organization = self.get_or_create_organization(self.parties, org_id)
                org_name = self.parser.find_text(touchpoint, "./cac:PartyName/cbc:Name")
                department = self.parser.find_text(touchpoint, "./cac:PostalAddress/cbc:Department")
                organization['name'] = f"{org_name} - {department}" if department else org_name

    def fetch_bt47_participants(self, root_element):
        """
        Fetch BT-47: Lot Participants and map to selectedParticipants array.
        """
        lots = root_element.findall(".//cac:ProcurementProjectLot", namespaces=self.parser.nsmap)
        for lot in lots:
            lot_id = self.parser.find_text(lot, "./cbc:ID")
            participants = lot.findall(".//cac:PreSelectedParty", namespaces=self.parser.nsmap)
            for participant in participants:
                party_name = self.parser.find_text(participant, "./cac:PartyName/cbc:Name")
                party_id = str(uuid.uuid4())
                self.parties.append({
                    "id": party_id,
                    "name": party_name,
                    "roles": ["selectedParticipant"]
                })
                for tender_lot in self.tender["lots"]:
                    if tender_lot["id"] == lot_id:
                        tender_lot.setdefault("designContest", {}).setdefault("selectedParticipants", []).append({"id": party_id, "name": party_name})

    def fetch_opt_300_procedure_service_provider(self, root_element):
        service_providers = root_element.findall(".//cac:ContractingParty/cac:ServiceProviderParty/cac:Party", namespaces=self.parser.nsmap)
        for svc_provider in service_providers:
            svc_provider_id = self.parser.find_text(svc_provider, "./cac:PartyIdentification/cbc:ID", namespaces=self.parser.nsmap)
            if svc_provider_id:
                org = self.get_or_create_organization(self.parties, svc_provider_id)
                if 'procurementServiceProvider' not in org.get('roles', []):
                    org.setdefault('roles', []).append('procurementServiceProvider')

                org_name = self.parser.find_text(
                    root_element, 
                    f".//efac:Organization[efac:Company/cac:PartyIdentification/cbc:ID='{svc_provider_id}']/efac:Company/cac:PartyName/cbc:Name", 
                    namespaces=self.parser.nsmap
                )
                if org_name:
                    org["name"] = org_name



    def fetch_bt508_buyer_profile(self, root_element):
        buyers = []
        profiles = root_element.findall(".//cac:ContractingParty", namespaces=self.parser.nsmap)
        for profile in profiles:
            buyer_uri = self.parser.find_text(profile, "./cbc:BuyerProfileURI", namespaces=self.parser.nsmap)
            buyers.append(buyer_uri)

        for uri in buyers:
            org_id = self.parser.find_text(profile, "./cac:Party/cac:PartyIdentification/cbc:ID", namespaces=self.parser.nsmap)
            organization = next((o for o in self.parties if o['id'] == org_id), None)
            if organization:
                organization.setdefault('details', {}).update({'buyerProfile': uri})
            else:
                organization = {
                    "id": org_id,
                    "roles": ["buyer"],
                    "details": {
                        "buyerProfile": uri,
                    }
                }
                self.parties.append(organization)
        return {}


    def fetch_bt610_activity_entity(self, root_element):
        activities = []
        contracting_parties = root_element.findall(".//cac:ContractingParty", namespaces=self.parser.nsmap)
        for party in contracting_parties:
            contracting_activity = party.find(".//cbc:ActivityTypeCode[@listName='entity-activity']", namespaces=self.parser.nsmap)
            if contracting_activity is not None and contracting_activity.text:
                activities.append({
                    "activityTypeCode": contracting_activity.text,
                })

        # Map the activity to the organization
        for activity in activities:
            org_id = self.parser.find_text(party, "./cac:Party/cac:PartyIdentification/cbc:ID", namespaces=self.parser.nsmap)
            scheme, code, description = self.map_activity_code(activity["activityTypeCode"], 'Activity')
            organization = next((o for o in self.parties if o['id'] == org_id), None)
            
            if organization:
                organization.setdefault("details", {}).setdefault("classifications", []).append({
                    "scheme": scheme,
                    "id": code,
                    "description": description
                })
            else:
                organization = {
                    "id": org_id,
                    "roles": ["buyer"],
                    "details": {
                        "classifications": [{
                            "scheme": scheme,
                            "id": code,
                            "description": description
                        }]
                    }
                }
                self.parties.append(organization)
        return {}

    def fetch_bt740_contracting_entity(self, element):
        contracting_parties = element.findall(".//cac:ContractingPartyType", namespaces=self.parser.nsmap)
        for party in contracting_parties:
            party_type_code = self.parser.find_text(party, "./cbc:PartyTypeCode[@listName='buyer-contracting-type']", namespaces=self.parser.nsmap)
            if party_type_code:
                org_id = self.parser.find_text(party, "./cac:Party/cac:PartyIdentification/cbc:ID", namespaces=self.parser.nsmap)
                description = self.get_contracting_entity_description(party_type_code)
                org = next((o for o in self.parties if o['id'] == org_id), None)

                if org:
                    org.setdefault("details", {}).setdefault("classifications", []).append({
                        "scheme": "eu-buyer-contracting-type",
                        "id": party_type_code,
                        "description": description
                    })
                else:
                    self.parties.append({
                        "id": org_id,
                        "roles": ["buyer"],
                        "details": {
                            "classifications": [{
                                "scheme": "eu-buyer-contracting-type",
                                "id": party_type_code,
                                "description": self.get_contracting_entity_description(party_type_code),
                            }]
                        }
                    })
        return {}

    
    def get_contracting_entity_description(self, code):
        # Define a mapping of contracting entity codes to descriptions
        contracting_entity_descriptions = {
            "cont-ent": "Contracting Entity",
            # Add other codes and descriptions as needed
        }
        return contracting_entity_descriptions.get(code, "Unknown contracting entity type")

    def fetch_opp_050_buyers_group_lead(self, root_element):
        groups = []
        parties = root_element.findall(".//efac:Organization", namespaces=self.parser.nsmap)
        for party in parties:
            group_lead_indicator = self.parser.find_text(party, "./efbc:GroupLeadIndicator", namespaces=self.parser.nsmap)
            if group_lead_indicator == 'true':
                groups.append({
                    "group_lead_indicator": group_lead_indicator,
                })
        
        for group in groups:
            org_id = str(uuid.uuid4())
            self.parties.append({
                "id": org_id,
                "roles": ["leadBuyer"]
            })
        return {}

    def fetch_opp_051_awarding_cpb_buyer(self, root_element):
        parties = root_element.findall(".//efac:Organization", namespaces=self.parser.nsmap)
        for party in parties:
            awarding_cpb_indicator = self.parser.find_text(party, "./efbc:AwardingCPBIndicator", namespaces=self.parser.nsmap)
            if awarding_cpb_indicator == "true":
                org_id = self.parser.find_text(party, "./efac:Company/cac:PartyIdentification/cbc:ID", namespaces=self.parser.nsmap)
                org = next((o for o in self.parties if o['id'] == org_id), None)
                if not org:
                    org = {
                        "id": org_id,
                        "roles": ["procuringEntity"]
                    }
                    self.parties.append(org)
                else:
                    if "procuringEntity" not in org['roles']:
                        org['roles'].append("procuringEntity")

    def fetch_opp_052_acquiring_cpb_buyer(self, root_element):
        parties = root_element.findall(".//efac:Organization", namespaces=self.parser.nsmap)
        for party in parties:
            acquiring_cpb_indicator = self.parser.find_text(party, "./efbc:AcquiringCPBIndicator", namespaces=self.parser.nsmap)
            if acquiring_cpb_indicator == "true":
                org_id = self.parser.find_text(party, "./efac:Company/cac:PartyIdentification/cbc:ID", namespaces=self.parser.nsmap)
                org = next((o for o in self.parties if o['id'] == org_id), None)
                if not org:
                    org = {
                        "id": org_id,
                        "roles": ["wholesaleBuyer"]
                    }
                    self.parties.append(org)
                else:
                    if "wholesaleBuyer" not in org['roles']:
                        org['roles'].append("wholesaleBuyer")
    
    def fetch_opt_030_service_type(self, root_element):
        contracting_parties = root_element.findall(".//cac:ContractingParty", namespaces=self.parser.nsmap)
        for party in contracting_parties:
            service_type_code = self.parser.find_text(party, "./cac:ServiceProviderParty/cbc:ServiceTypeCode", namespaces=self.parser.nsmap)
            if service_type_code:
                org_id = self.parser.find_text(party, "./cac:ServiceProviderParty/cac:Party/cac:PartyIdentification/cbc:ID", namespaces=self.parser.nsmap)
                org = next((o for o in self.parties if o['id'] == org_id), None)
                if not org:
                    org = {
                        "id": org_id,
                        "roles": []
                    }

                    if service_type_code == "serv-prov":
                        org["roles"].append("procurementServiceProvider")
                    elif service_type_code == "ted-esen":
                        org["roles"].append("eSender")
                    
                    self.parties.append(org)
                else:
                    if service_type_code == "serv-prov" and "procurementServiceProvider" not in org['roles']:
                        org['roles'].append("procurementServiceProvider")
                    elif service_type_code == "ted-esen" and "eSender" not in org['roles']:
                        org['roles'].append("eSender")

    def fetch_opt_170_tender_leader(self, root):
        tenderers = root.findall(".//efac:NoticeResult/efac:TenderingParty/efac:Tenderer", namespaces=self.parser.nsmap)
        for tenderer in tenderers:
            group_lead_indicator = self.parser.find_text(tenderer, "./efbc:GroupLeadIndicator", namespaces=self.parser.nsmap)
            if group_lead_indicator == "true":
                org_id = self.parser.find_text(tenderer, "./cbc:ID", namespaces=self.parser.nsmap)
                org = next((o for o in self.parties if o["id"] == org_id), None)
                if not org:
                    org = {
                        "id": org_id,
                        "roles": ["leadTenderer", "tenderer"]
                    }
                    self.parties.append(org)
                else:
                    if "leadTenderer" not in org["roles"]:
                        org["roles"].append("leadTenderer")
                    if "tenderer" not in org["roles"]:
                        org["roles"].append("tenderer")
    
    def fetch_opt_300_signatory_reference(self, root_element):
        signatory_parties = root_element.findall(".//efac:NoticeResult/efac:SettledContract/cac:SignatoryParty", namespaces=self.parser.nsmap)
        for signatory_party in signatory_parties:
            signatory_id = self.parser.find_text(signatory_party, "./cac:PartyIdentification/cbc:ID", namespaces=self.parser.nsmap)
            if signatory_id:
                org = next((o for o in self.parties if o["id"] == signatory_id), None)
                if not org:
                    # Get organization's name
                    name = self.parser.find_text(root_element, f"//efac:Organizations/efac:Organization[efac:Company/cac:PartyIdentification/cbc:ID[text()='{signatory_id}']]/efac:Company/cac:PartyName/cbc:Name", namespaces=self.parser.nsmap)
                    org = {
                        "id": signatory_id,
                        "name": name,
                        "roles": ["buyer"]
                    }
                    self.parties.append(org)

                contract_id = self.parser.find_text(signatory_party, './../../cbc:ID', namespaces=self.parser.nsmap)  # Current contract ID
                for award in self.awards:
                    if contract_id in award.get("relatedContracts", []):
                        if "buyers" not in award:
                            award["buyers"] = []
                        award["buyers"].append({"id": signatory_id})

    def fetch_opt_300_buyer_technical_reference(self, root_element):
        buyer_parties = root_element.findall(".//cac:ContractingParty", namespaces=self.parser.nsmap)
        for buyer_party in buyer_parties:
            buyer_id = self.parser.find_text(buyer_party, "./cac:Party/cac:PartyIdentification/cbc:ID", namespaces=self.parser.nsmap)
            if buyer_id:
                org = next((o for o in self.parties if o["id"] == buyer_id), None)
                if not org:
                    org = {
                        "id": buyer_id,
                        "roles": ["buyer"]
                    }
                    self.parties.append(org)
                else:
                    if "buyer" not in org.get('roles', []):
                        org['roles'].append("buyer")
    
    def fetch_opt_301_tenderer_maincont(self, root_element):
        notice_results = root_element.findall(".//efac:NoticeResult", namespaces=self.parser.nsmap)
        for notice_result in notice_results:
            lot_tenders = notice_result.findall(".//efac:LotTender", namespaces=self.parser.nsmap)
            for lot_tender in lot_tenders:
                tender_id = self.parser.find_text(lot_tender, "./cbc:ID", namespaces=self.parser.nsmap)
                subcontractors = lot_tender.findall(".//efac:SubContractor", namespaces=self.parser.nsmap)
                for subcontractor in subcontractors:
                    subcontractor_id = self.parser.find_text(subcontractor, "./cbc:ID", namespaces=self.parser.nsmap)
                    main_contractors = subcontractor.findall(".//efac:MainContractor", namespaces=self.parser.nsmap)
                    for main_contractor in main_contractors:
                        main_contractor_id = self.parser.find_text(main_contractor, "./cbc:ID", namespaces=self.parser.nsmap)

                        if main_contractor_id:
                            main_contractor_org = next((o for o in self.parties if o['id'] == main_contractor_id), None)
                            if not main_contractor_org:
                                main_contractor_org = {
                                    "id": main_contractor_id,
                                    "roles": ["tenderer"]
                                }
                                self.parties.append(main_contractor_org)
                            else:
                                if "tenderer" not in main_contractor_org.get('roles', []):
                                    main_contractor_org['roles'].append("tenderer")
                        
                        bid = next((b for b in self.tender["bids"]["details"] if b['id'] == tender_id), None)
                        if not bid:
                            bid = {
                                "id": tender_id,
                                "subcontracting": {
                                    "subcontracts": []
                                }
                            }
                            self.tender["bids"]["details"].append(bid)
                        
                        subcontract = next((s for s in bid["subcontracting"]["subcontracts"]
                                            if s["subcontractor"]["id"] == subcontractor_id), None)
                        if not subcontract:
                            subcontract = {
                                "id": str(len(bid["subcontracting"]["subcontracts"]) + 1),
                                "subcontractor": {
                                    "id": subcontractor_id
                                },
                                "mainContractors": []
                            }
                            bid["subcontracting"]["subcontracts"].append(subcontract)

                        main_contractor_references = {
                            "id": main_contractor_id
                        }
                        subcontract["mainContractors"].append(main_contractor_references)

    def fetch_opt_310_tender(self, root_element):
        if "bids" not in self.tender:
            self.tender["bids"] = {"details": []}

        notice_results = root_element.findall(".//efac:NoticeResult", namespaces=self.parser.nsmap)
        for notice_result in notice_results:
            lot_tenders = notice_result.findall(".//efac:LotTender", namespaces=self.parser.nsmap)
            for lot_tender in lot_tenders:
                tender_id = self.parser.find_text(lot_tender, "./cbc:ID", namespaces=self.parser.nsmap)
                tender_party_id = self.parser.find_text(lot_tender, "./efac:TenderingParty/cbc:ID", namespaces=self.parser.nsmap)

                bidder_details = {
                    "id": tender_id,
                    "tenderers": []
                }

                tendering_parties = notice_result.findall(f".//efac:TenderingParty[cbc:ID='{tender_party_id}']", namespaces=self.parser.nsmap)
                for tendering_party in tendering_parties:
                    tenderers = tendering_party.findall(".//efac:Tenderer", namespaces=self.parser.nsmap)
                    for tenderer in tenderers:
                        org_id = self.parser.find_text(tenderer, "./cbc:ID", namespaces=self.parser.nsmap)
                        if org_id:
                            org = next((o for o in self.parties if o['id'] == org_id), None)
                            if org:
                                if "tenderer" not in org.get('roles', []):
                                    org['roles'].append("tenderer")
                            else:
                                self.parties.append({
                                    "id": org_id,
                                    "roles": ["tenderer"]
                                })

                            bidder_details["tenderers"].append({
                                "id": org_id
                            })

                self.tender["bids"]["details"].append(bidder_details)

    def fetch_opt_301_add_info_provider(self, root_element):
        lots = root_element.findall(".//cac:ProcurementProjectLot", namespaces=self.parser.nsmap)
        for lot in lots:
            additional_info_party_id = self.parser.find_text(lot, "./cac:TenderingTerms/cac:AdditionalInformationParty/cac:PartyIdentification/cbc:ID", namespaces=self.parser.nsmap)
            if additional_info_party_id:
                org = next((o for o in self.parties if o["id"] == additional_info_party_id), None)
                if not org:
                    org = {
                        "id": additional_info_party_id,
                        "roles": ["processContactPoint"]
                    }
                    self.parties.append(org)
                else:
                    if "processContactPoint" not in org["roles"]:
                        org["roles"].append("processContactPoint")
    
    def fetch_opt_301_lot_employ_legis(self, root_element):
        lot_elements = root_element.findall(".//cac:ProcurementProjectLot", namespaces=self.parser.nsmap)
        for lot in lot_elements:
            lot_id = self.parser.find_text(lot, "./cbc:ID", namespaces=self.parser.nsmap)
            legis_doc_elements = lot.findall(".//cac:EmploymentLegislationDocumentReference", namespaces=self.parser.nsmap)
            for legis_doc in legis_doc_elements:
                doc_id = self.parser.find_text(legis_doc, "./cbc:ID", namespaces=self.parser.nsmap)
                issuer_party_id = self.parser.find_text(legis_doc, "./cac:IssuerParty/cac:PartyIdentification/cbc:ID", namespaces=self.parser.nsmap)
                if doc_id and issuer_party_id:
                    document = {
                        "id": doc_id,
                        "relatedLots": [lot_id],
                        "publisher": {
                            "id": issuer_party_id
                        }
                    }
                    self.add_update_document(document)
                    organization = self.get_or_create_organization(self.parties, issuer_party_id)
                    if 'informationService' not in organization['roles']:
                        organization['roles'].append('informationService')

    def fetch_opt_301_lot_environ_legis(self, root_element):
        lot_elements = root_element.findall(".//cac:ProcurementProjectLot", namespaces=self.parser.nsmap)
        for lot in lot_elements:
            lot_id = self.parser.find_text(lot, "./cbc:ID", namespaces=self.parser.nsmap)
            legis_doc_elements = lot.findall(".//cac:EnvironmentalLegislationDocumentReference", namespaces=self.parser.nsmap)
            for legis_doc in legis_doc_elements:
                doc_id = self.parser.find_text(legis_doc, "./cbc:ID", namespaces=self.parser.nsmap)
                issuer_party_id = self.parser.find_text(legis_doc, "./cac:IssuerParty/cac:PartyIdentification/cbc:ID", namespaces=self.parser.nsmap)
                if doc_id and issuer_party_id:
                    document = {
                        "id": doc_id,
                        "relatedLots": [lot_id],
                        "publisher": {
                            "id": issuer_party_id
                        }
                    }
                    self.add_update_document(document)
                    organization = self.get_or_create_organization(self.parties, issuer_party_id)
                    if 'informationService' not in organization['roles']:
                        organization['roles'].append('informationService')
                                                               

    def fetch_listed_on_regulated_market(self, org_element):
        indicator = self.parser.find_text(org_element, "./efbc:ListedOnRegulatedMarketIndicator", namespaces=self.parser.nsmap)
        if indicator is not None:
            return indicator.lower() == 'true'
        return None
    
    def fetch_company_size(self, org_element):
        size = self.parser.find_text(org_element, "./efac:Company/efbc:CompanySizeCode", namespaces=self.parser.nsmap)
        return size.lower() if size else None
    
    def fetch_is_natural_person(self, org_element):
        indicator = self.parser.find_text(org_element, "./efbc:NaturalPersonIndicator", namespaces=self.parser.nsmap)
        if indicator is not None:
            return indicator.lower() == 'true'
        return None
    
    def fetch_bid_variant(self, root_element):
        for bid_element in root_element.findall(".//efac:LotTender", namespaces=self.parser.nsmap):
            bid_id = self.parser.find_text(bid_element, "./cbc:ID", namespaces=self.parser.nsmap)
            variant_indicator = self.parser.find_text(bid_element, "./efbc:TenderVariantIndicator", namespaces=self.parser.nsmap)
            if variant_indicator:
                variant_value = variant_indicator.lower() == 'true'
                bid_details = next((b for b in self.bids.get("details", []) if b["id"] == bid_id), None)
                if bid_details:
                    bid_details["variant"] = variant_value
                else:
                    self.bids.setdefault("details", []).append({
                        "id": bid_id,
                        "variant": variant_value
                    })

    def fetch_bt500_company_organization(self, root_element):
        logger = logging.getLogger(__name__)
        organizations = []

        organization_elements = root_element.findall(".//efac:Organizations/efac:Organization", namespaces=self.parser.nsmap)

        for org_element in organization_elements:
            org_id = self.parser.find_text(org_element, "./efac:Company/cac:PartyIdentification/cbc:ID", namespaces=self.parser.nsmap)
            if org_id:
                logger.debug(f"Parsing organization with ID: {org_id}")

                organization = self.get_or_create_organization(organizations, org_id)
                logger.debug(f"Initial organization data: {json.dumps(organization, indent=2, ensure_ascii=False)}")

                org_name = self.parser.find_text(org_element, "./efac:Company/cac:PartyName/cbc:Name", namespaces=self.parser.nsmap)
                if org_name:
                    logger.debug(f"Found organization name: {org_name}")
                    department = self.parser.find_text(org_element, "./efac:Company/cac:PostalAddress/cbc:Department", namespaces=self.parser.nsmap)
                    organization['name'] = f"{org_name} - {department}" if department else org_name

                company_id = self.parser.find_text(org_element, "./efac:Company/cac:PartyLegalEntity/cbc:CompanyID", namespaces=self.parser.nsmap)
                if company_id:
                    if not any(identifier['id'] == company_id for identifier in organization.get("additionalIdentifiers", [])):
                        organization.setdefault("additionalIdentifiers", []).append({"id": company_id, "scheme": "CompanyID"})

                address_element = org_element.find('./efac:Company/cac:PostalAddress', namespaces=self.parser.nsmap)
                if address_element is not None:
                    logger.debug(f"Found address element for organization ID: {org_id}")
                    organization['address'] = {
                        "streetAddress": self.process_street_address(address_element, self.parser.nsmap),
                        "locality": self.parser.find_text(address_element, './cbc:CityName', namespaces=self.parser.nsmap),
                        "region": self.parser.find_text(address_element, './cbc:CountrySubentity', namespaces=self.parser.nsmap),
                        "postalCode": self.parser.find_text(address_element, './cbc:PostalZone', namespaces=self.parser.nsmap),
                        "country": self.convert_language_code(self.parser.find_text(address_element, './cac:Country/cbc:IdentificationCode', namespaces=self.parser.nsmap), code_type='country')
                    }

                logger.debug(f"Organization with address: {json.dumps(organization, indent=2, ensure_ascii=False)}")

                # Handle the contact point
                contact_point = self.fetch_bt502_contact_point(org_element)
                if contact_point:
                    logger.debug(f"Found contact point: {contact_point}")
                    organization['contactPoint'] = contact_point

                self.add_or_update_party(organizations, organization)
            else:
                logger.warning('Party element found without an ID or Name!')

            # Beneficial Owners
            ubo_elements = org_element.findall(".//efac:UltimateBeneficialOwner", namespaces=self.parser.nsmap)
            for ubo_element in ubo_elements:
                ubo_id = self.parser.find_text(ubo_element, "./cbc:ID", namespaces=self.parser.nsmap)
                if ubo_id:
                    logger.debug(f"Processing UBO with ID: {ubo_id}")
                    family_name = self.parser.find_text(ubo_element, './cbc:FamilyName', namespaces=self.parser.nsmap) or ""
                    first_name = self.parser.find_text(ubo_element, './cbc:FirstName', namespaces=self.parser.nsmap) or ""
                    full_name = f"{first_name} {family_name}".strip()

                    raw_nationality_code = self.parser.find_text(ubo_element, "./efac:Nationality/cbc:NationalityID", namespaces=self.parser.nsmap)
                    processed_nationality_code = self.convert_language_code(raw_nationality_code, 'country') if raw_nationality_code else None

                    ubo_info = {
                        "id": ubo_id,
                        "name": full_name,
                        "nationality": processed_nationality_code
                    }
                    phone_info = self.fetch_bt503_ubo_contact(ubo_element)
                    if phone_info:
                        ubo_info.update(phone_info)

                    organization.setdefault("beneficialOwners", []).append(ubo_info)
                    logger.debug(f"Updated organization with UBO: {organization}")

        return organizations

    def process_street_address(self, address_element, nsmap):
        street_name = address_element.find('./cbc:StreetName', namespaces=nsmap)
        additional_street_name = address_element.find('./cbc:AdditionalStreetName', namespaces=nsmap)
        address_lines = address_element.findall('./cac:AddressLine/cbc:Line', namespaces=nsmap)
        
        parts = [part.text for part in [street_name, additional_street_name] + address_lines if part is not None and part.text]
        return ', '.join(parts)
    
    def fetch_bt500_touchpoint_organization(self, element):
        xpath = ".//efac:Organizations/efac:Organization/efac:TouchPoint/cac:PartyName/cbc:Name"
        name = self.parser.find_text(element, xpath, namespaces=self.parser.nsmap)
        ident_xpath = ".//efac:Organizations/efac:Organization/efac:TouchPoint/cac:PartyIdentification/cbc:ID"
        identifier = self.parser.find_text(element, ident_xpath, namespaces=self.parser.nsmap)
        company_id_xpath = ".//efac:Organizations/efac:Organization/efac:Company/cac:PartyLegalEntity/cbc:CompanyID"
        company_id = self.parser.find_text(element, company_id_xpath, namespaces=self.parser.nsmap)
        touchpoint_country_xpath = ".//efac:Organizations/efac:Organization/efac:TouchPoint/cac:PostalAddress/cac:Country/cbc:IdentificationCode"
        touchpoint_country = self.parser.find_text(element, touchpoint_country_xpath, namespaces=self.parser.nsmap)
        touchpoint_country_code = self.convert_language_code(touchpoint_country, code_type='country') if touchpoint_country else None
        touchpoint_department = self.parser.find_text(element, ".//efac:Organizations/efac:Organization/efac:TouchPoint/cac:PostalAddress/cbc:Department", namespaces=self.parser.nsmap)

        if identifier:
            organization = self.get_or_create_organization(self.parties, identifier)

            if name:
                org_name = f"{name} - {touchpoint_department}" if touchpoint_department else name
                organization['name'] = org_name

            if company_id:
                organization.setdefault("identifier", {})
                organization["identifier"]["id"] = company_id
                organization["identifier"]["scheme"] = "internal"

            if touchpoint_country_code:
                organization['address'] = {"country": touchpoint_country_code}

            self.add_or_update_party(self.parties, organization)

        return organization if identifier else {}
    
    def fetch_bt502_contact_point(self, org_element):
        contact_point = {}
        contact_name = self.parser.find_text(org_element, "./efac:Company/cac:Contact/cbc:Name", namespaces=self.parser.nsmap)
        telephone = self.parser.find_text(org_element, "./efac:Company/cac:Contact/cbc:Telephone", namespaces=self.parser.nsmap)
        email = self.parser.find_text(org_element, "./efac:Company/cac:Contact/cbc:ElectronicMail", namespaces=self.parser.nsmap)

        if contact_name:
            contact_point["name"] = contact_name
        if telephone:
            contact_point["telephone"] = telephone
        if email:
            contact_point["email"] = email

        logger.debug(f"Extracted contact point: {contact_point}")
        return contact_point if contact_point else {}

    def fetch_bt503_ubo_contact(self, ubo_element):
        telephone = self.parser.find_text(ubo_element, "./cac:Contact/cbc:Telephone", namespaces=self.parser.nsmap)
        return {"telephone": telephone} if telephone else {}
    
    def parse_organizations(self, element):
        organizations = []
        org_elements = element.findall(".//efac:Organization", namespaces=self.parser.nsmap)

        for org_element in org_elements:
            org_id = self.parser.find_text(org_element, "./efac:Company/cac:PartyIdentification/cbc:ID", namespaces=self.parser.nsmap)
            if org_id:
                logging.debug(f"Processing organization with ID: {org_id}")

                organization = self.get_or_create_organization(organizations, org_id)
                logging.debug(f"Retrieved organization: {organization}")

                org_name = self.parser.find_text(org_element, "./efac:Company/cac:PartyName/cbc:Name", namespaces=self.parser.nsmap)
                department = self.parser.find_text(org_element, "./efac:Company/cac:PostalAddress/cbc:Department", namespaces=self.parser.nsmap)
                org_name_full = f"{org_name} - {department}" if department else org_name

                contact_point = self.fetch_bt502_contact_point(org_element)
                logging.debug(f"Extracted contact point: {contact_point}")

                address = {
                    'locality': self.parser.find_text(org_element, './efac:Company/cac:PostalAddress/cbc:CityName', namespaces=self.parser.nsmap),
                    'postalCode': self.parser.find_text(org_element, './efac:Company/cac:PostalAddress/cbc:PostalZone', namespaces=self.parser.nsmap),
                    'country': self.convert_language_code(self.parser.find_text(org_element, './efac:Company/cac:PostalAddress/cac:Country/cbc:IdentificationCode', namespaces=self.parser.nsmap), 'country'),
                    'region': self.parser.find_text(org_element, './efac:Company/cac:PostalAddress/cbc:CountrySubentityCode', namespaces=self.parser.nsmap)
                }

                identifier = {
                    'id': self.parser.find_text(org_element, './efac:Company/cac:PartyLegalEntity/cbc:CompanyID', namespaces=self.parser.nsmap),
                    'scheme': 'GB-COH'
                }

                updated_info = {
                    'roles': [],
                    'name': org_name_full,
                    'address': address,
                    'identifier': identifier,
                    'contactPoint': contact_point
                }

                self.update_organization(organization, updated_info)
                logging.debug(f"Updated organization info: {organization}")

                # Beneficial Owners
                ubo_elements = org_element.findall(".//efac:UltimateBeneficialOwner", namespaces=self.parser.nsmap)
                for ubo_element in ubo_elements:
                    ubo_id = self.parser.find_text(ubo_element, "./cbc:ID", namespaces=self.parser.nsmap)
                    if ubo_id:
                        logging.debug(f"Processing UBO with ID: {ubo_id}")
                        first_name = self.parser.find_text(ubo_element, './cbc:FirstName', namespaces=self.parser.nsmap) or ""
                        family_name = self.parser.find_text(ubo_element, './cbc:FamilyName', namespaces=self.parser.nsmap) or ""
                        full_name = f"{first_name} {family_name}".strip()

                        raw_nationality_code = self.parser.find_text(ubo_element, "./efac:Nationality/cbc:NationalityID", namespaces=self.parser.nsmap)
                        processed_nationality_code = self.convert_language_code(raw_nationality_code, 'country') if raw_nationality_code else None

                        ubo_info = {
                            "id": ubo_id,
                            "name": full_name,
                            "nationality": processed_nationality_code
                        }
                        phone_info = self.fetch_bt503_ubo_contact(ubo_element)
                        if phone_info:
                            ubo_info.update(phone_info)

                        organization.setdefault("beneficialOwners", []).append(ubo_info)
                        logging.debug(f"Updated organization with UBO: {organization}")

                # Address, Listed on Market, and Company Size
                organization['address'] = self.process_ubo_address(org_element)
                organization['listedOnRegulatedMarket'] = self.fetch_listed_on_regulated_market(org_element)
                organization['scale'] = self.fetch_company_size(org_element)

            return organizations
    
    def fetch_bt503_touchpoint_contact(self, org_element):
        telephone = self.parser.find_text(org_element, "./efac:TouchPoint/cac:Contact/cbc:Telephone", namespaces=self.parser.nsmap)
        return {"telephone": telephone} if telephone else {}

    def get_dispatch_date_time(self):
        root = self.parser.root
        issue_date = self.parser.find_text(root, ".//cbc:IssueDate", namespaces=self.parser.nsmap)
        issue_time = self.parser.find_text(root, ".//cbc:IssueTime", namespaces=self.parser.nsmap)

        if issue_date and issue_time:
            combined_datetime = f"{issue_date[:10]}T{issue_time[:8]}{issue_date[10:]}"

            try:
                parsed_datetime = datetime.fromisoformat(combined_datetime)
                return parsed_datetime.isoformat()
            except ValueError as e:
                logging.error(f"Error parsing dispatch date/time: {combined_datetime} - {e}")
        else:
            logging.warning("Missing issue date or issue time in the XML.")

        return None

    def get_contract_signed_date(self):
        root = self.parser.root
        issue_date = self.parser.find_text(root, ".//efac:SettledContract/cbc:IssueDate")
        if issue_date:
            try:
                parsed_date = datetime.fromisoformat(issue_date)
                return parsed_date.isoformat()
            except ValueError as e:
                logging.error(f"Error parsing contract signed date: {issue_date} - {e}")
        return None

    def get_legal_basis(self, element):
        legal_basis = {}
        document_references = element.findall(".//cac:TenderingTerms/cac:ProcurementLegislationDocumentReference", namespaces=self.parser.nsmap)

        for ref in document_references:
            id_text = self.parser.find_text(ref, "./cbc:ID")
            if id_text not in ['CrossBorderLaw', 'LocalLegalBasis']:
                legal_basis['id'] = id_text
                legal_basis['scheme'] = 'ELI'
                description = self.parser.find_text(ref, "./cbc:DocumentDescription")
                if description:
                    legal_basis['description'] = description
                break
            elif id_text == 'LocalLegalBasis':
                legal_basis['id'] = 'LocalLegalBasis'
                description = self.parser.find_text(ref, "./cbc:DocumentDescription")
                if description:
                    legal_basis['description'] = description
                break

        if 'id' not in legal_basis:
            celex_code = self.parser.find_text(element, ".//cbc:RegulatoryDomain")
            if celex_code:
                legal_basis['id'] = celex_code
                legal_basis['scheme'] = 'CELEX'

        return legal_basis

    def fetch_bt506_emails(self, root_element):
        for org_element in root_element.findall(".//efac:Organization", namespaces=self.parser.nsmap):
            org_id = self.parser.find_text(org_element, "./efac:Company/cac:PartyIdentification/cbc:ID", namespaces=self.parser.nsmap)
            if org_id:
                company_email = self.parser.find_text(org_element, "./efac:Company/cac:Contact/cbc:ElectronicMail", namespaces=self.parser.nsmap)
                touchpoint_email = self.parser.find_text(org_element, "./efac:TouchPoint/cac:Contact/cbc:ElectronicMail", namespaces=self.parser.nsmap)

                if company_email:
                    self.add_or_update_party(self.parties, {
                        "id": org_id,
                        "contactPoint": {"email": company_email}
                    })
                    
                if touchpoint_email:
                    self.add_or_update_party(self.parties, {
                        "id": org_id,
                        "contactPoint": {"email": touchpoint_email}
                    })

        for ubo_element in root_element.findall(".//efac:UltimateBeneficialOwner", namespaces=self.parser.nsmap):
            ubo_id = self.parser.find_text(ubo_element, "./cbc:ID", namespaces=self.parser.nsmap)
            email = self.parser.find_text(ubo_element, "./cac:Contact/cbc:ElectronicMail", namespaces=self.parser.nsmap)
            org_id = self.parser.find_text(ubo_element.getparent(), "./efac:Company/cac:PartyIdentification/cbc:ID", namespaces=self.parser.nsmap)

            if ubo_id and email:
                ubo_info = {
                    "id": ubo_id,
                    "email": email
                }

                organization = next((o for o in self.parties if o['id'] == org_id), None)
                if not organization:
                    organization = {
                        "id": org_id,
                        "beneficialOwners": [ubo_info]
                    }
                    self.parties.append(organization)
                else:
                    organization.setdefault('beneficialOwners', []).append(ubo_info)

    def fetch_bt505_urls(self, root_element):
        for org_element in root_element.findall(".//efac:Organization", namespaces=self.parser.nsmap):
            org_id = self.parser.find_text(org_element, "./efac:Company/cac:PartyIdentification/cbc:ID", namespaces=self.parser.nsmap)
            if org_id:
                company_url = self.parser.find_text(org_element, "./efac:Company/cbc:WebsiteURI", namespaces=self.parser.nsmap)
                touchpoint_url = self.parser.find_text(org_element, "./efac:TouchPoint/cbc:WebsiteURI", namespaces=self.parser.nsmap)

                if company_url:
                    self.add_or_update_party(self.parties, {
                        "id": org_id,
                        "details": {"url": company_url}
                    })
                    
                if touchpoint_url:
                    self.add_or_update_party(self.parties, {
                        "id": org_id,
                        "details": {"url": touchpoint_url}
                    })

    def fetch_urls_for_lot(self, lot_element, scheme_name):
        lot_id = self.parser.find_attribute(lot_element, "./cbc:ID", "schemeName")
        if lot_id == scheme_name:
            auction_url = self.parser.find_text(
                lot_element, "./cac:TenderingProcess/cac:AuctionTerms/cbc:AuctionURI", namespaces=self.parser.nsmap)
            submission_url = self.parser.find_text(
                lot_element, "./cac:TenderingTerms/cac:TenderRecipientParty/cbc:EndpointID", namespaces=self.parser.nsmap)
            
            documents = []
            call_for_tenders_documents = self.parser.find_nodes(
                lot_element, "./cac:TenderingTerms/cac:CallForTendersDocumentReference")
            
            for doc in call_for_tenders_documents:
                doc_id = self.parser.find_text(doc, "./cbc:ID", namespaces=self.parser.nsmap)
                if doc_id:
                    doc_url = self.parser.find_text(
                        doc, 
                        "./cac:Attachment[cbc:DocumentType/text()='non-restricted-document']/cac:ExternalReference/cbc:URI", 
                        namespaces=self.parser.nsmap)
                    restricted_url = self.parser.find_text(
                        doc, 
                        "./cac:Attachment[cbc:DocumentType/text()='restricted-document']/cac:ExternalReference/cbc:URI", 
                        namespaces=self.parser.nsmap)
                    
                    if doc_url:
                        documents.append({
                            "id": doc_id,
                            "documentType": "biddingDocuments",
                            "url": doc_url,
                            "relatedLots": [lot_id]
                        })
                    
                    if restricted_url:
                        documents.append({
                            "id": doc_id,
                            "accessDetailsURL": restricted_url,
                            "relatedLots": [lot_id]
                        })
            
            for document in documents:
                self.add_update_document(document)
            
            return auction_url, submission_url
        return None, None
    
    def add_update_document(self, new_document):
        """Adds or updates the document object in tender.documents list."""
        found = False
        for doc in self.tender.get("documents", []):
            if doc["id"] == new_document["id"]:
                doc.update(new_document)
                found = True
                break
        if not found:
            self.tender.setdefault("documents", []).append(new_document)

    @staticmethod
    def get_or_create_organization(organizations, org_id):
        for organization in organizations:
            if organization['id'] == org_id:
                return organization
        new_organization = {
            "id": org_id,
            "roles": [],
        }
        organizations.append(new_organization)
        return new_organization
    
    @staticmethod
    def update_organization(organization, new_info):
        if 'roles' in new_info and new_info['roles']:
            organization['roles'] = list(set(organization['roles'] + new_info['roles']))
        
        if 'address' in new_info and new_info['address']:
            organization['address'] = new_info['address']
        
        if 'identifier' in new_info and new_info['identifier']:
            organization['identifier'] = new_info['identifier']
        
        if 'contactPoint' in new_info and new_info['contactPoint']:
            organization['contactPoint'] = new_info['contactPoint']
        
        if 'details' in new_info and new_info['details']:
            organization['details'] = new_info['details']
    
    def process_ubo_address(self, address_element):
        country_element = self.parser.find_text(address_element, './cac:Country/cbc:IdentificationCode', namespaces=self.parser.nsmap)
        region_element = self.parser.find_text(address_element, './cbc:CountrySubentityCode', namespaces=self.parser.nsmap)
        return {
            'country': self.convert_language_code(country_element, code_type='country'),
            'region': region_element
        } if country_element or region_element else {}

    def get_activity_description(self, activity_code):
        activity_descriptions = {
            "airport": "Airport-related activities",
            "defence": "Defence",
            "econ-aff": "Economic affairs",
            "education": "Education",
            "electricity": "Electricity-related activities",
            "env-pro": "Environmental protection",
            "gas-heat": "Production, transport or distribution of gas or heat",
            "gas-oil": "Extraction of gas or oil",
            "gen-pub": "General public services",
			"hc-am": "Housing and community amenities",
            "health": "Health",
            "port": "Port-related activities",
            "post": "Postal services",
            "pub-os": "Public order and safety",
            "rail": "Railway services",
            "rcr": "Recreation, culture and religion",
            "soc-pro": "Social protection",
			"solid-fuel": "Exploration or extraction of coal or other solid fuels",	
            "urttb": "Urban railway, tramway, trolleybus or bus services",
            "water": "Water-related activities"
        }
        return activity_descriptions.get(activity_code, "")
    
    def parse_activity_authority(self, element):
        activities = []
        activity_elements = element.findall(".//cac:ContractingParty/cac:ContractingActivity/cbc:ActivityTypeCode[@listName='authority-activity']", namespaces=self.parser.nsmap)
        for activity in activity_elements:
            activity_code = activity.text
            if activity_code:
                scheme, code, description = self.map_activity_code(activity_code, 'Authority')
                activities.append({
                    "scheme": scheme,
                    "id": code,
                    "description": description
                })
        return activities

    def parse_buyer_legal_type(self, root_element):
        legal_types = []
        party_elements = root_element.findall(".//cac:ContractingParty/cac:ContractingPartyType/cbc:PartyTypeCode[@listName='buyer-legal-type']", namespaces=self.parser.nsmap)
        for element in party_elements:
            party_type_code = element.text
            if party_type_code:
                legal_types.append({
                    "scheme": "TED_CA_TYPE",
                    "id": party_type_code,
                    "description": self.get_buyer_legal_type_description(party_type_code)
                })
        return legal_types

    def get_buyer_legal_type_description(self, code):
        # Define a mapping of buyer legal type codes to short descriptions
        legal_type_mapping = {
            "body-pl": "Body governed by public law",
            "body-pl-cga": "Body governed by public law, controlled by a central government authority",
            "body-pl-la": "Body governed by public law, controlled by a local authority",
            "body-pl-ra": "Body governed by public law, controlled by a regional authority",
            "cga": "Central government authority",
            "def-cont": "Defence contractor",
            "eu-ins-bod-ag": "EU institution, body or agency",
            "eu-int-org": "European Institution/Agency or International Organisation",
            "grp-p-aut": "Group of public authorities",
            "int-org": "International organisation",
            "la": "Local authority",
            "org-sub": "Organisation awarding a contract subsidised by a contracting authority",
            "org-sub-cga": "Organisation awarding a contract subsidised by a central government authority",
            "org-sub-la": "Organisation awarding a contract subsidised by a local authority",
            "org-sub-ra": "Organisation awarding a contract subsidised by a regional authority",
            "pub-undert": "Public undertaking",
            "pub-undert-cga": "Public undertaking, controlled by a central government authority",
            "pub-undert-la": "Public undertaking, controlled by a local authority",
            "pub-undert-ra": "Public undertaking, controlled by a regional authority",
            "ra": "Regional authority",
            "rl-aut": "Regional or local authority",
            "spec-rights-entity": "Entity with special or exclusive rights",
        }

        return legal_type_mapping.get(code, "Unknown legal type")

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
        return self.form_type_mapping.get(form_type_code, {'tag': [], 'tender_status': 'planned'})

    def parse_lots(self, element):
        lots = []
        lot_elements = element.findall(".//cac:ProcurementProjectLot", namespaces=self.parser.nsmap)

        for lot_element in lot_elements:
            lot_id = self.parser.find_text(lot_element, "./cbc:ID")
            lot_title = self.parser.find_text(lot_element, ".//cac:ProcurementProject/cbc:Name")
            gpa_indicator = self.parser.find_text(lot_element, "./cac:TenderingProcess/cbc:GovernmentAgreementConstraintIndicator") == 'true'
            estimated_value_element = self.parser.find_node(lot_element, ".//cac:ProcurementProject/cac:RequestedTenderTotal/cbc:EstimatedOverallContractAmount")

            lot = {
                "id": lot_id,
                "title": lot_title,
                "description": self.parser.find_text(lot_element, ".//cac:ProcurementProject/cbc:Description"),
                "awardCriteria": self.parse_award_criteria(lot_element),
                "mainProcurementCategory": self.parser.find_text(lot_element, ".//cac:ProcurementProject/cbc:ProcurementTypeCode[@listName='contract-nature']"),
                "reviewDetails": self.parser.find_text(lot_element, ".//cac:TenderingTerms/cac:AppealTerms/cac:SpecialTerms/cbc:Description"),
                "coveredBy": ["GPA"] if gpa_indicator else None,
                "techniques": {
                    "hasElectronicAuction": self.parser.find_text(lot_element, ".//cac:TenderingProcess/cac:AuctionTerms/cbc:AuctionConstraintIndicator") == 'true'
                },
                "identifiers": {
                    "id": self.parser.find_text(lot_element, ".//cbc:ID"),
                    "scheme": "internal"
                },
                "items": self.parse_items(lot_element)
            }
            if estimated_value_element is not None:
                lot["value"] = {
                    "amount": float(estimated_value_element.text) if estimated_value_element.text else None,
                    "currency": estimated_value_element.get('currencyID')
                }

            contract_period = self.parse_contract_period_for_lot(lot_element)
            if contract_period:
                lot['contractPeriod'] = contract_period

            options_description = self.parser.find_text(lot_element, "./cac:ProcurementProject/cac:ContractExtension/cbc:OptionsDescription", namespaces=self.parser.nsmap)
            if options_description:
                lot['options'] = {"description": options_description}

            self.process_lot_realized_location(lot_element, lot)

            lots.append(lot)

        return lots
    
    def parse_lot_group(self, lot_element):
        lot_id = self.parser.find_attribute(lot_element, "./cbc:ID", "schemeName")
        if lot_id == 'LotsGroup':
            estimated_value = self.parser.find_text(lot_element, ".//cac:ProcurementProject/cac:RequestedTenderTotal/cbc:EstimatedOverallContractAmount", namespaces=self.parser.nsmap)
            currency_id = self.parser.find_attribute(lot_element, ".//cac:ProcurementProject/cac:RequestedTenderTotal/cbc:EstimatedOverallContractAmount", "currencyID", namespaces=self.parser.nsmap)

            return {
                "id": self.parser.find_text(lot_element, "./cbc:ID", namespaces=self.parser.nsmap),
                "maximumValue": {
                    "amount": float(estimated_value) if estimated_value else None,
                    "currency": currency_id
                }
            }
        return None
    
    def parse_single_lot(self, lot_element):
        lot_id = self.parser.find_text(lot_element, "./cbc:ID")
        lot_title = self.parser.find_text(lot_element, ".//cac:ProcurementProject/cbc:Name", namespaces=self.parser.nsmap)
        gpa_indicator = self.parser.find_text(lot_element, "./cac:TenderingProcess/cbc:GovernmentAgreementConstraintIndicator", namespaces=self.parser.nsmap) == 'true'

        # Fetching the estimated overall contract amount for the lot
        estimated_value_element = lot_element.find("./cac:ProcurementProject/cac:RequestedTenderTotal/cbc:EstimatedOverallContractAmount", namespaces=self.parser.nsmap)
        estimated_value = estimated_value_element.text if estimated_value_element is not None else None
        currency_id = estimated_value_element.get('currencyID') if estimated_value_element is not None else None

        lot = {
            "id": lot_id,
            "title": lot_title,
            "items": self.parse_items(lot_element)
        }

        # BT-23-Lot: Main Nature
        main_nature_code = self.parser.find_text(lot_element, "./cac:ProcurementProject/cbc:ProcurementTypeCode[@listName='contract-nature']")
        if main_nature_code:
            if main_nature_code in ['works', 'services']:
                lot['mainProcurementCategory'] = main_nature_code
            elif main_nature_code == 'supplies':
                lot['mainProcurementCategory'] = 'goods'

        # Only add value if an estimated value is provided
        if estimated_value is not None and currency_id is not None:
            lot['value'] = {
                "amount": float(estimated_value),
                "currency": currency_id
            }

        # Include 'coveredBy' key only if the gpa_indicator is true
        if gpa_indicator:
            lot['coveredBy'] = ["GPA"]

        contract_period = self.parse_contract_period_for_lot(lot_element)
        if contract_period:
            lot['contractPeriod'] = contract_period

        options_description = self.parser.find_text(lot_element, "./cac:ProcurementProject/cac:ContractExtension/cbc:OptionsDescription", namespaces=self.parser.nsmap)
        if options_description:
            lot['options'] = {"description": options_description}

        # Fetch and process realized location country sub-division code (NUTS)
        self.process_lot_realized_location(lot_element, lot)

        return lot
    
    def process_lot_realized_location(self, lot_element, lot):
        realized_locations = self.parser.find_nodes(lot_element, "./cac:ProcurementProject/cac:RealizedLocation/cac:Address")
        if realized_locations:
            lot.setdefault('deliveryAddresses', [])
            for location in realized_locations:
                realized_location = {
                    "region": self.parser.find_text(location, "./cbc:CountrySubentityCode", namespaces=self.parser.nsmap),
                }
                if realized_location:
                    lot['deliveryAddresses'].append(realized_location)

    def parse_contract_period_for_lot(self, lot_element):
        start_date = self.parser.find_text(lot_element, ".//cac:PlannedPeriod/cbc:StartDate", namespaces=self.parser.nsmap)
        end_date = self.parser.find_text(lot_element, ".//cac:PlannedPeriod/cbc:EndDate", namespaces=self.parser.nsmap)
        contract_period = {}
        if start_date:
            contract_period['startDate'] = parse_iso_date(start_date).isoformat()
        if end_date:
            contract_period['endDate'] = parse_iso_date(end_date).isoformat()
        return contract_period if contract_period else None

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

    def parse_award_criteria(self, lot_element):
        award_criteria = {
            "weightingDescription": self.parser.find_text(lot_element, ".//cac:TenderingTerms/cac:AwardingTerms/cac:AwardingCriterion/cbc:CalculationExpression"),
            "criteria": []
        }

        criteria_elements = lot_element.findall(".//cac:TenderingTerms/cac:AwardingTerms/cac:AwardingCriterion/cac:SubordinateAwardingCriterion", namespaces=self.parser.nsmap)

        for criterion in criteria_elements:
            criterion_details = {}

            criterion_type = self.parser.find_text(criterion, "./cbc:AwardingCriterionTypeCode[@listName='award-criterion-type']")
            if criterion_type:
                criterion_details['type'] = criterion_type

            criterion_description = self.parser.find_text(criterion, "./cbc:Description")
            if criterion_description:
                criterion_details['description'] = criterion_description

            award_criterion_parameters = criterion.findall(".//ext:UBLExtensions/ext:UBLExtension/ext:ExtensionContent/efext:EformsExtension/efac:AwardCriterionParameter", namespaces=self.parser.nsmap)
            for param in award_criterion_parameters:
                param_list_name = self.parser.find_attribute(param, ".//efbc:ParameterCode", "listName")
                param_value = self.parser.find_text(param, ".//efbc:ParameterNumeric") or self.parser.find_text(param, ".//efbc:ParameterCode")

                if param_list_name and param_value:
                    number_details = {"number": float(param_value)}

                    if param_list_name == 'number-weight':
                        number_details['weight'] = self.map_award_criterion_number_weight(param_value)
                    elif param_list_name == 'number-fixed':
                        number_details['fixed'] = self.map_award_criterion_number_fixed(param_value)
                    elif param_list_name == 'number-threshold':
                        number_details['threshold'] = self.map_award_criterion_number_threshold(param_value)

                    criterion_details.setdefault('numbers', []).append(number_details)

            criterion_name = self.parser.find_text(criterion, "./cbc:Name")
            if criterion_name:
                criterion_details['name'] = criterion_name

            award_criteria["criteria"].append(criterion_details)

        return award_criteria if award_criteria["criteria"] else None
    
    def map_award_criterion_number_weight(self, param_value):
        mapping = {
            "percentageExact": "percentageExact",
            # Add more mappings if needed
        }
        return mapping.get(param_value, param_value)

    def map_award_criterion_number_fixed(self, param_value):
        mapping = {
            "total": "total",
            # Add more mappings if needed
        }
        return mapping.get(param_value, param_value)

    def map_award_criterion_number_threshold(self, param_value):
        mapping = {
            "maximumBids": "maximumBids",
            # Add more mappings if needed
        }
        return mapping.get(param_value, param_value)
    
    def parse_bt06_lot_strategic_procurement(self, lot_element):
        strategic_procurement_elements = lot_element.findall(".//cac:ProcurementProject/cac:ProcurementAdditionalType/cbc:ProcurementTypeCode[@listName='strategic-procurement']", namespaces=self.parser.nsmap)
        
        sustainability = []

        strategies = ["awardCriteria", "contractPerformanceConditions", "selectionCriteria", "technicalSpecifications"]

        for element in strategic_procurement_elements:
            code = element.text
            if code and code != "none":
                sustainability.append({
                    "goal": self.map_strategic_procurement_code(code),
                    "strategies": strategies
                })

        return sustainability if sustainability else None
    
    def map_strategic_procurement_code(self, code):
        mapping = {
            "inn-pur": "economic.innovativePurchase",
            # Add more mappings if required
        }
        return mapping.get(code, code)

    def fetch_notice_language(self, root_element):
        notice_language_code = self.parser.find_text(root_element, ".//cbc:NoticeLanguageCode")
        if notice_language_code:
            language_iso = self.convert_language_code(notice_language_code, 'language')
            return language_iso.lower() if language_iso else None
        return None

    def convert_language_code(self, code, code_type='language'):
        language_mapping = {
            'ENG': 'en',
            'FRA': 'fr',
            'DEU': 'de',
            'ITA': 'it',
            'ESP': 'es',
            'NLD': 'nl',
            'BGR': 'bg',
            'CES': 'cs',
            'DAN': 'da',
            'ELL': 'el',
            'EST': 'et',
            'FIN': 'fi',
            'HUN': 'hu',
            'HRV': 'hr',
            'LAT': 'lv',
            'LIT': 'lt',
            'MLT': 'mt',
            'POL': 'pl',
            'POR': 'pt',
            'RON': 'ro',
            'SLK': 'sk',
            'SLV': 'sl',
            'SWE': 'sv',
            'NOR': 'no',
            'ISL': 'is'
        }

        if code_type == 'language':
            return language_mapping.get(code.upper(), code.lower())
        return None
   
    def parse_tender_values(self, root):
        tender_values = []
        tender_value_elements = root.findall(".//ext:UBLExtensions/ext:UBLExtension/ext:ExtensionContent/efext:EformsExtension/efac:NoticeResult/efac:LotTender", namespaces=self.parser.nsmap)
            
        for tender_value_element in tender_value_elements:
            tender_id = self.parser.find_text(tender_value_element, "./cbc:ID")
            payable_amount_element = tender_value_element.find("./cac:LegalMonetaryTotal/cbc:PayableAmount", namespaces=self.parser.nsmap)
            
            if tender_id and payable_amount_element is not None:
                tender_values.append({
                    "id": tender_id,
                    "value": {
                        "amount": float(payable_amount_element.text) if payable_amount_element.text else None,
                        "currency": payable_amount_element.get('currencyID')
                    },
                    "relatedLot": self.parser.find_text(tender_value_element, "./efac:TenderLot/cbc:ID")
                })

        return tender_values
    
    def handle_bt14_and_bt707(self, root_element):
        lots = self.parser.find_nodes(root_element, ".//cac:ProcurementProjectLot")
        for lot in lots:
            lot_id = self.parser.find_text(lot, "./cbc:ID")
            document_elements = self.parser.find_nodes(lot, "./cac:TenderingTerms/cac:CallForTendersDocumentReference")
            for document in document_elements:
                document_id = self.parser.find_text(document, "./cbc:ID")
                document_type = self.parser.find_text(document, "./cbc:DocumentType")
                document_type_code = self.parser.find_text(document, "./cbc:DocumentTypeCode")
                if document_type == 'restricted-document':
                    self.tender.setdefault("documents", []).append({
                        "id": document_id,
                        "documentType": "biddingDocuments",
                        "accessDetails": "Restricted.",
                        "relatedLots": [lot_id]
                    })
                    if document_type_code:
                        self.tender["documents"][-1]["accessDetails"] = self.get_access_details_from_code(document_type_code)
        
    def get_access_details_from_code(self, code):
        access_details_mapping = {
            "ipr-iss": "Restricted. Intellectual property rights issues",
            # Add more mappings as needed
        }
        return access_details_mapping.get(code, "")

    def add_update_award(self, new_award):
        """
        Updates the internal awards data structure.
        If an award with the given ID exists, it updates it; otherwise, it adds a new entry.
        """
        found = False
        for idx, award in enumerate(self.awards):
            if award["id"] == new_award["id"]:
                self.awards[idx] = new_award
                found = True
                break
        if not found:
            self.awards.append(new_award)
    
    def parse_items(self, lot_element):
        items = []
        project_element = self.parser.find_nodes(lot_element, "./cac:ProcurementProject")[0]
        classifications = self.parse_classifications(project_element)
        
        for idx, classification in enumerate(classifications, 1):
            items.append({
                "id": str(idx),
                "classification": classification,
                "relatedLot": self.parser.find_text(lot_element, "./cbc:ID")
            })
        return items


    def fetch_bt300_additional_info(self, root):
        # Path to extract the additional information as per BT-300
        additional_info_element = root.find(".//cac:ProcurementProject/cbc:Note", namespaces=self.parser.nsmap)
        return additional_info_element.text if additional_info_element is not None else None

    def parse_procedure_type(self, root_element):
        procedure_type_code = self.parser.find_text(root_element, ".//cac:TenderingProcess/cbc:ProcedureCode[@listName='procurement-procedure-type']", namespaces=self.parser.nsmap)
        if procedure_type_code:
            # Assuming a mapping dictionary or method that maps procedure type code to procurement method
            procurement_method_mapping = {
                "open": {"method": "open", "details": "Open procedure"},
                "restricted": {"method": "selective", "details": "Restricted procedure"},
                "negotiated": {"method": "limited", "details": "Negotiated procedure"},
                # Add more mappings as needed
            }
            return procurement_method_mapping.get(procedure_type_code)
        return None

    def parse_direct_award_justification(self, root_element):
        justification_text_xpath = (
            ".//cac:ProcessJustification"
            "[cac:ProcessReasonCode[@listName='direct-award-justification']]/cac:ProcessReason"
        )
        justification_code_xpath = (
            ".//cac:ProcessJustification"
            "[cac:ProcessReasonCode[@listName='direct-award-justification']]/cac:ProcessReasonCode"
        )

        # Separate paths to ensure full namespace prefixing
        paths = {
            'justification_text': ".//cac:ProcessJustification[cac:ProcessReasonCode[contains(@listName, 'direct-award-justification')]]/cac:ProcessReason",
            'justification_code': ".//cac:ProcessJustification[cac:ProcessReasonCode[contains(@listName, 'direct-award-justification')]]/cac:ProcessReasonCode"
        }
        
        # Use xpath to handle cases inside lxml with proper prefixing
        justification_text = root_element.xpath(paths['justification_text'], namespaces=self.parser.nsmap)
        justification_code = root_element.xpath(paths['justification_code'], namespaces=self.parser.nsmap)

        # Get the first element text if exists.
        justification_text = justification_text[0].text if justification_text else None
        justification_code = justification_code[0].text if justification_code else None

        rationale_classifications = []
        if justification_code:
            classification = {
                "id": justification_code,
                "description": self.get_direct_award_justification_description(justification_code),
                "scheme": "eu-direct-award-justification"
            }
            rationale_classifications.append(classification)
        
        return justification_text, rationale_classifications

    def handle_bidding_documents(self, root_element):
        # BT-15: Lot - Documents URL
        lot_elements = root_element.xpath("//cac:ProcurementProjectLot[cbc:ID/@schemeName='Lot']", namespaces=self.parser.nsmap)
        for lot_elem in lot_elements:
            lot_id = self.parser.find_text(lot_elem, "./cbc:ID", namespaces=self.parser.nsmap)
            document_references = self.parser.find_nodes(lot_elem, "./cac:TenderingTerms/cac:CallForTendersDocumentReference")
            for doc_ref in document_references:
                doc_id = self.parser.find_text(doc_ref, "./cbc:ID", namespaces=self.parser.nsmap)
                uri = self.parser.find_text(doc_ref, "./cac:Attachment[../cbc:DocumentType='non-restricted-document']/cac:ExternalReference/cbc:URI", namespaces=self.parser.nsmap)
                if uri:
                    document = {
                        "id": doc_id,
                        "documentType": "biddingDocuments",
                        "relatedLots": [lot_id],
                        "url": uri
                    }
                    self.add_update_document(document)
        
        # BT-15: Part - Documents URL
        part_elements = root_element.xpath("//cac:ProcurementProjectLot[cbc:ID/@schemeName='Part']", namespaces=self.parser.nsmap)
        for part_elem in part_elements:
            document_references = self.parser.find_nodes(part_elem, "./cac:TenderingTerms/cac:CallForTendersDocumentReference")
            for doc_ref in document_references:
                doc_id = self.parser.find_text(doc_ref, "./cbc:ID", namespaces=self.parser.nsmap)
                uri = self.parser.find_text(doc_ref, "./cac:Attachment[../cbc:DocumentType='non-restricted-document']/cac:ExternalReference/cbc:URI", namespaces=self.parser.nsmap)
                if uri:
                    document = {
                        "id": doc_id,
                        "documentType": "biddingDocuments",
                        "url": uri
                    }
                    self.add_update_document(document)

        # BT-151: Contract URL
        settled_contracts = root_element.xpath("//efac:NoticeResult/efac:SettledContract", namespaces=self.parser.nsmap)
        for contract in settled_contracts:
            contract_id = self.parser.find_text(contract, "./cbc:ID", namespaces=self.parser.nsmap)
            uri = self.parser.find_text(contract, "./cbc:URI", namespaces=self.parser.nsmap)
            if uri:
                document = {
                    "id": str(len(self.get_contracts()) + 1),
                    "documentType": "contractSigned",
                    "url": uri
                }
                self.add_update_contract_document(contract_id, document)

        # BT-615: Lot - Documents Restricted URL
        self.handle_restricted_docs(root_element, scheme="Lot")
        
        # BT-615: Part - Documents Restricted URL
        self.handle_restricted_docs(root_element, scheme="Part")

        # OPT-110: Lot - Fiscal Legislation URL
        self.handle_fiscal_legislation(root_element, scheme="Lot")
        
        # OPT-110: Part - Fiscal Legislation URL
        self.handle_fiscal_legislation(root_element, scheme="Part")

        # OPT-111: Lot - Fiscal Legislation Document ID
        self.handle_fiscal_doc_id(root_element, scheme="Lot")
        
        # OPT-111: Part - Fiscal Legislation Document ID
        self.handle_fiscal_doc_id(root_element, scheme="Part")

        # OPT-120: Lot - Environmental Legislation URL
        self.handle_environmental_legis(root_element, scheme="Lot")
        
        # OPT-120: Part - Environmental Legislation URL
        self.handle_environmental_legis(root_element, scheme="Part")

        # OPT-130: Lot - Employment Legislation URL
        self.handle_employment_legis(root_element, scheme="Lot")
        
        # OPT-130: Part - Employment Legislation URL
        self.handle_employment_legis(root_element, scheme="Part")

    def handle_restricted_docs(self, root_element, scheme):
        elements = root_element.xpath(f"//cac:ProcurementProjectLot[cbc:ID/@schemeName='{scheme}']", namespaces=self.parser.nsmap)
        for elem in elements:
            lot_id = self.parser.find_text(elem, "./cbc:ID", namespaces=self.parser.nsmap)
            document_references = self.parser.find_nodes(elem, "./cac:TenderingTerms/cac:CallForTendersDocumentReference")
            for doc_ref in document_references:
                doc_id = self.parser.find_text(doc_ref, "./cbc:ID", namespaces=self.parser.nsmap)
                uri = self.parser.find_text(doc_ref, "./cac:Attachment[../cbc:DocumentType='restricted-document']/cac:ExternalReference/cbc:URI", namespaces=self.parser.nsmap)
                if uri:
                    document = {
                        "id": doc_id,
                        "accessDetailsURL": uri,
                        "relatedLots": [lot_id]
                    }
                    self.add_update_document(document)

    def handle_fiscal_legislation(self, root_element, scheme):
        elements = root_element.xpath(f"//cac:ProcurementProjectLot[cbc:ID/@schemeName='{scheme}']/cac:TenderingTerms/cac:FiscalLegislationDocumentReference/cac:Attachment/cac:ExternalReference/cbc:URI", namespaces=self.parser.nsmap)
        for elem in elements:
            lot_id = self.parser.find_text(elem, "./../../../../cbc:ID", namespaces=self.parser.nsmap)
            doc_id = self.parser.find_text(elem, "./../../cbc:ID", namespaces=self.parser.nsmap)
            uri = elem.text
            document = {
                "id": doc_id,
                "url": uri,
                "relatedLots": [lot_id]
            }
            self.add_update_document(document)

    def handle_fiscal_doc_id(self, root_element, scheme):
        elements = root_element.xpath(f"//cac:ProcurementProjectLot[cbc:ID/@schemeName='{scheme}']/cac:TenderingTerms/cac:FiscalLegislationDocumentReference/cbc:ID", namespaces=self.parser.nsmap)
        for elem in elements:
            lot_id = self.parser.find_text(elem, "./../../../../cbc:ID", namespaces=self.parser.nsmap)
            doc_id = elem.text
            document = {
                "id": doc_id,
                "documentType": "legislation",
                "relatedLots": [lot_id]
            }
            self.add_update_document(document)

    def handle_environmental_legis(self, root_element, scheme):
        elements = root_element.xpath(f"//cac:ProcurementProjectLot[cbc:ID/@schemeName='{scheme}']/cac:TenderingTerms/cac:EnvironmentalLegislationDocumentReference/cac:Attachment/cac:ExternalReference/cbc:URI", namespaces=self.parser.nsmap)
        for elem in elements:
            lot_id = self.parser.find_text(elem, "./../../../../cbc:ID", namespaces=self.parser.nsmap)
            doc_id = self.parser.find_text(elem, "./../../cbc:ID", namespaces=self.parser.nsmap)
            uri = elem.text
            document = {
                "id": doc_id,
                "url": uri,
                "relatedLots": [lot_id]
            }
            self.add_update_document(document)

    def handle_employment_legis(self, root_element, scheme):
        elements = root_element.xpath(f"//cac:ProcurementProjectLot[cbc:ID/@schemeName='{scheme}']/cac:TenderingTerms/cac:EmploymentLegislationDocumentReference/cac:Attachment/cac:ExternalReference/cbc:URI", namespaces=self.parser.nsmap)
        for elem in elements:
            lot_id = self.parser.find_text(elem, "./../../../../cbc:ID", namespaces=self.parser.nsmap)
            doc_id = self.parser.find_text(elem, "./../../cbc:ID", namespaces=self.parser.nsmap)
            uri = elem.text
            document = {
                "id": doc_id,
                "url": uri,
                "relatedLots": [lot_id]
            }
            self.add_update_document(document)

    def add_update_contract_document(self, contract_id, document):
        contract = next((c for c in self.get_contracts() if c['id'] == contract_id), None)
        if contract:
            contract.setdefault('documents', []).append(document)
        else:
            self.awards.append({
                "id": contract_id,
                "documents": [document]
            })

    def get_contracts(self):
        return self.awards

    def get_direct_award_justification_description(self, code):
        # Assuming a mapping dictionary or method that maps justification codes to their descriptions
        justification_mapping = {
            "ecom-excl": "Specific exclusion in the field of electronic communications",
            "urgent": "Urgent needs due to unforeseen circumstances",
            # Add more mappings as needed
        }
        return justification_mapping.get(code, "")

    def parse_procedure_features(self, root_element):
        return self.parser.find_text(root_element, ".//cac:TenderingProcess/cbc:Description", namespaces=self.parser.nsmap)
    
    def remove_schema_from_identifier(self, data):
        """
        Recursively remove the 'scheme' key from the 'identifier' dictionary within the data structure.
        """
        if isinstance(data, list):
            for item in data:
                self.remove_schema_from_identifier(item)
        elif isinstance(data, dict):
            for key, value in list(data.items()):
                if key == "identifier" and isinstance(value, dict) and "scheme" in value:
                    del value["scheme"]
                else:
                    self.remove_schema_from_identifier(value)
        return data
    
    def parse_classifications(self, element):
        classifications = []
        items = []
        item_id = 1

        # Parse BT-26(a) Procedure Additional Classifications
        additional_class_elements = element.findall(".//cac:ProcurementProject/cac:AdditionalCommodityClassification", namespaces=self.parser.nsmap)
        for element in additional_class_elements:
            scheme = self.parser.find_attribute(element, "./cbc:ItemClassificationCode", "listName").upper()
            code = self.parser.find_text(element, "./cbc:ItemClassificationCode").strip()
            classifications.append({
                "scheme": scheme,
                "id": code
            })

        # Parse BT-262 Procedure Main Classification
        main_class_element = element.find(".//cac:ProcurementProject/cac:MainCommodityClassification", namespaces=self.parser.nsmap)
        if main_class_element is not None:
            scheme = self.parser.find_attribute(main_class_element, "./cbc:ItemClassificationCode", "listName").upper()
            code = self.parser.find_text(main_class_element, "./cbc:ItemClassificationCode").strip()
            items.append({
                "id": str(item_id),
                "classification": {
                    "scheme": scheme,
                    "id": code
                }
            })

        # Parse BT-26(m) Lot Additional Classifications
        lot_elements = element.findall(".//cac:ProcurementProjectLot", namespaces=self.parser.nsmap)
        for lot_element in lot_elements:
            lot_id = self.parser.find_text(lot_element, "./cbc:ID", namespaces=self.parser.nsmap)

            additional_class_elements = lot_element.findall(".//cac:ProcurementProject/cac:AdditionalCommodityClassification", namespaces=self.parser.nsmap)
            for element in additional_class_elements:
                scheme = self.parser.find_attribute(element, "./cbc:ItemClassificationCode", "listName").upper()
                code = self.parser.find_text(element, "./cbc:ItemClassificationCode").strip()
                items.append({
                    "id": str(item_id),
                    "classification": {
                        "scheme": scheme,
                        "id": code
                    },
                    "relatedLot": lot_id
                })

            # Parse BT-262 Lot Main Classification
            main_class_element = lot_element.find(".//cac:ProcurementProject/cac:MainCommodityClassification", namespaces=self.parser.nsmap)
            if main_class_element is not None:
                scheme = self.parser.find_attribute(main_class_element, "./cbc:ItemClassificationCode", "listName").upper()
                code = self.parser.find_text(main_class_element, "./cbc:ItemClassificationCode").strip()
                items.append({
                    "id": str(item_id),
                    "classification": {
                        "scheme": scheme,
                        "id": code
                    },
                    "relatedLot": lot_id
                })

        return items

                    
    def fetch_opt_301_lot_mediator(self, root_element):
        # OPT-301-Lot-Mediator: Mediator Technical Identifier Reference
        lots = root_element.xpath(".//cac:ProcurementProjectLot[cbc:ID/@schemeName='Lot']", namespaces=self.parser.nsmap)
        for lot in lots:
            mediator_id = self.parser.find_text(lot, ".//cac:TenderingTerms/cac:AppealTerms/cac:MediationParty/cac:PartyIdentification/cbc:ID", namespaces=self.parser.nsmap)
            if mediator_id:
                existing_org = next((org for org in self.parties if org['id'] == mediator_id), None)
                if existing_org:
                    if 'mediationBody' not in existing_org['roles']:
                        existing_org['roles'].append('mediationBody')
                else:
                    self.parties.append({
                        "id": mediator_id,
                        "roles": ["mediationBody"]
                    })

    def fetch_opt_301_lot_review_org(self, root_element):
        # OPT-301-Lot-ReviewOrg: Review Organization Technical Identifier Reference
        lots = root_element.xpath(".//cac:ProcurementProjectLot[cbc:ID/@schemeName='Lot']", namespaces=self.parser.nsmap)
        for lot in lots:
            review_org_id = self.parser.find_text(lot, ".//cac:TenderingTerms/cac:AppealTerms/cac:AppealReceiverParty/cac:PartyIdentification/cbc:ID", namespaces=self.parser.nsmap)
            if review_org_id:
                existing_org = next((org for org in self.parties if org['id'] == review_org_id), None)
                if existing_org:
                    if 'reviewBody' not in existing_org['roles']:
                        existing_org['roles'].append('reviewBody')
                else:
                    self.parties.append({
                        "id": review_org_id,
                        "roles": ["reviewBody"]
                    })

    def fetch_opt_301_part_review_org(self, root_element):
        # OPT-301-Part-ReviewOrg: Review Organization Technical Identifier Reference for Parts
        parts = root_element.xpath(".//cac:ProcurementProjectLot[cbc:ID/@schemeName='Part']", namespaces=self.parser.nsmap)
        for part in parts:
            review_org_id = self.parser.find_text(part, ".//cac:TenderingTerms/cac:AppealTerms/cac:AppealReceiverParty/cac:PartyIdentification/cbc:ID", namespaces=self.parser.nsmap)
            if review_org_id:
                existing_org = next((org for org in self.parties if org['id'] == review_org_id), None)
                if existing_org:
                    if 'reviewBody' not in existing_org['roles']:
                        existing_org['roles'].append('reviewBody')
                else:
                    self.parties.append({
                        "id": review_org_id,
                        "roles": ["reviewBody"]
                    })

    def add_or_update_lot(self, lots, lot_info):
        """
        Adds or updates a lot in the lots list.
        If a lot with the same ID exists, it updates the existing lot.
        Otherwise, it adds a new lot to the list.
        """
        for lot in lots:
            if lot['id'] == lot_info['id']:
                for key, value in lot_info.items():
                    if key in lot and isinstance(value, dict):
                        lot[key].update(value)
                    else:
                        lot[key] = value
                return
        lots.append(lot_info)

    
    def clean_release_structure(self, data):
        if isinstance(data, dict):
            cleaned = {k: self.clean_release_structure(v) for k, v in data.items() if v is not None and v != {} and v != []}
            return {k: v for k, v in cleaned.items() if v}
        elif isinstance(data, list):
            return [self.clean_release_structure(v) for v in data if v is not None and v != {} and v != []]
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
    
    def fetch_tender_estimated_value(self, root):
       value_element = root.find(".//cac:ProcurementProject/cac:RequestedTenderTotal/cbc:EstimatedOverallContractAmount", namespaces=self.parser.nsmap)
       if value_element is not None:
           amount = float(value_element.text) if value_element.text else None
           currency = value_element.get('currencyID')
           return {"amount": amount, "currency": currency}
       return None

    def fetch_bt13713_lotresult(self, root_element):
        lot_results = root_element.findall(".//efac:NoticeResult/efac:LotResult", namespaces=self.parser.nsmap)
        for lot_result in lot_results:
            result_id = self.parser.find_text(lot_result, "./cbc:ID", namespaces=self.parser.nsmap)
            if result_id:
                lot_id = self.parser.find_text(lot_result, "./efac:TenderLot/cbc:ID", namespaces=self.parser.nsmap)
                self.add_or_update_award(result_id)
                self.add_or_update_award_related_lots(result_id, [lot_id])

    def add_or_update_award_related_lots(self, award_id, related_lots):
        award = next((a for a in self.awards if a['id'] == award_id), None)
        if award:
            for lot_id in related_lots:
                if lot_id not in award['relatedLots']:
                    award['relatedLots'].append(lot_id)
        else:
            self.awards.append({"id": award_id, "relatedLots": related_lots})

    def add_or_update_award(self, award_id):
        award = next((a for a in self.awards if a['id'] == award_id), None)
        if not award:
            self.awards.append({"id": award_id, "relatedLots": []})

    def fetch_bt142_winner_chosen(self, root_element):
        lot_results = root_element.findall(".//efac:NoticeResult/efac:LotResult", namespaces=self.parser.nsmap)
        for lot_result in lot_results:
            result_id = self.parser.find_text(lot_result, "./cbc:ID", namespaces=self.parser.nsmap)
            if result_id:
                tender_result_code = self.parser.find_text(lot_result, "./cbc:TenderResultCode", namespaces=self.parser.nsmap)
                if tender_result_code == 'selec-w':
                    self.update_award_status(result_id, 'active', 'At least one winner was chosen.')
                elif tender_result_code == 'open-nw':
                    self.update_lot_status(result_id, 'active')
                elif tender_result_code == 'clos-nw':
                    self.update_award_status(result_id, 'unsuccessful', 'No winner chosen.')

    def update_award_status(self, award_id, status, status_details=None):
        award = next((a for a in self.awards if a['id'] == award_id), None)
        if award:
            award['status'] = status
            if status_details:
                award['statusDetails'] = status_details

    def update_lot_status(self, lot_id, status):
        for lot in self.tender.get('lots', []):
            if lot['id'] == lot_id:
                lot['status'] = status
                break                    

    def fetch_bt144_not_awarded_reason(self, root_element):
        lot_results = root_element.findall(".//efac:NoticeResult/efac:LotResult", namespaces=self.parser.nsmap)
        for lot_result in lot_results:
            result_id = self.parser.find_text(lot_result, "./cbc:ID", namespaces=self.parser.nsmap)
            if result_id:
                decision_reason_code = self.parser.find_text(lot_result, "./efac:DecisionReason/efbc:DecisionReasonCode", namespaces=self.parser.nsmap)
                if decision_reason_code:
                    self.update_award_status(result_id, 'unsuccessful', self.get_non_award_reason(decision_reason_code))

    def get_non_award_reason(self, code):
        reasons = {
            "no-rece": "No tenders, requests to participate or projects were received",
            # Add other mappings as needed
        }
        return reasons.get(code, "Unknown reason")
    
    def fetch_bt1451_winner_decision_date(self, root_element):
        settled_contracts = root_element.findall(".//efac:NoticeResult/efac:SettledContract", namespaces=self.parser.nsmap)
        for contract in settled_contracts:
            contract_id = self.parser.find_text(contract, "./cbc:ID", namespaces=self.parser.nsmap)
            award_date = self.parser.find_text(contract, "./cbc:AwardDate", namespaces=self.parser.nsmap)
            if contract_id and award_date:
                lot_results = contract.xpath("ancestor::efac:NoticeResult/efac:LotResult[efac:SettledContract/cbc:ID='" + contract_id + "']", namespaces=self.parser.nsmap)
                for lot_result in lot_results:
                    result_id = self.parser.find_text(lot_result, "./cbc:ID", namespaces=self.parser.nsmap)
                    if result_id:
                        self.update_award_date(result_id, award_date)

    def update_award_date(self, award_id, date):
        award = next((a for a in self.awards if a['id'] == award_id), None)
        if award:
            existing_date = award.get('date')
            new_date = parse_iso_date(date).isoformat() if date else None
            if not existing_date or (new_date and new_date < existing_date):
                award['date'] = new_date

    def fetch_bt163_concession_value_description(self, root_element):
        lot_tenders = root_element.findall(".//efac:NoticeResult/efac:LotTender", namespaces=self.parser.nsmap)
        for lot_tender in lot_tenders:
            tender_id = self.parser.find_text(lot_tender, "./cbc:ID", namespaces=self.parser.nsmap)
            value_description = self.parser.find_text(lot_tender, "./efac:ConcessionRevenue/efbc:ValueDescription", namespaces=self.parser.nsmap)
            if tender_id and value_description:
                lot_result_id = self.parser.find_text(lot_tender.getparent(), "./efac:LotResult/cbc:ID", namespaces=self.parser.nsmap)
                if lot_result_id:
                    self.add_or_update_concession_value_description(lot_result_id, value_description)

    def add_or_update_concession_value_description(self, award_id, description):
        award = next((a for a in self.awards if a['id'] == award_id), None)
        if award:
            award['valueCalculationMethod'] = description

    def fetch_bt3202_contract_tender_reference(self, root_element):
        settled_contracts = root_element.findall(".//efac:NoticeResult/efac:SettledContract", namespaces=self.parser.nsmap)
        for contract in settled_contracts:
            tender_id = self.parser.find_text(contract, "./efac:LotTender/cbc:ID", namespaces=self.parser.nsmap)
            contract_id = self.parser.find_text(contract, "./cbc:ID", namespaces=self.parser.nsmap)
            if tender_id and contract_id:
                self.add_or_update_contract_related_bids(contract_id, tender_id)
                self.handle_tendering_party(contract_id, tender_id)

    def add_or_update_contract_related_bids(self, contract_id, tender_id):
        contract = next((c for c in self.get_contracts() if c['id'] == contract_id), None)
        if not contract:
            contract = {"id": contract_id, "relatedBids": [tender_id]}
            self.get_contracts().append(contract)
        else:
            if tender_id not in contract.get('relatedBids', []):
                contract.setdefault('relatedBids', []).append(tender_id)

    def add_supplier_to_award(self, contract_id, supplier_id):
        for award in self.awards:
            for contract in award.get('contracts', []):
                if contract['id'] == contract_id:
                    if 'suppliers' not in award:
                        award['suppliers'] = []
                    if not any(s['id'] == supplier_id for s in award['suppliers']):
                        award['suppliers'].append({'id': supplier_id})

    def fetch_bt660_framework_re_estimated_value(self, root_element):
        lot_results = root_element.findall(".//efac:NoticeResult/efac:LotResult", namespaces=self.parser.nsmap)
        for lot_result in lot_results:
            result_id = self.parser.find_text(lot_result, "./cbc:ID", namespaces=self.parser.nsmap)
            if result_id:
                reestimated_value_element = lot_result.find("./efac:FrameworkAgreementValues/efbc:ReestimatedValueAmount", namespaces=self.parser.nsmap)
                if reestimated_value_element is not None:
                    reestimated_value = float(reestimated_value_element.text) if reestimated_value_element.text else None
                    currency_id = reestimated_value_element.get('currencyID')
                    if reestimated_value and currency_id:
                        self.update_award_estimated_value(result_id, reestimated_value, currency_id)

    def update_award_estimated_value(self, award_id, amount, currency):
        award = next((a for a in self.awards if a['id'] == award_id), None)
        if award:
            award['estimatedValue'] = {"amount": amount, "currency": currency}  

    def fetch_bt709_framework_maximum_value(self, root_element):
        lot_results = root_element.findall(".//efac:NoticeResult/efac:LotResult", namespaces=self.parser.nsmap)
        for lot_result in lot_results:
            result_id = self.parser.find_text(lot_result, "./cbc:ID", namespaces=self.parser.nsmap)
            if result_id:
                maximum_value_element = lot_result.find("./efac:FrameworkAgreementValues/cbc:MaximumValueAmount", namespaces=self.parser.nsmap)
                if maximum_value_element is not None:
                    maximum_value = float(maximum_value_element.text) if maximum_value_element.text else None
                    currency_id = maximum_value_element.get('currencyID')
                    if maximum_value and currency_id:
                        self.update_award_maximum_value(result_id, maximum_value, currency_id)

    def update_award_maximum_value(self, award_id, amount, currency):
        award = next((a for a in self.awards if a['id'] == award_id), None)
        if award:
            award['maximumValue'] = {"amount": amount, "currency": currency}                  

    def fetch_bt720_tender_value(self, root_element):
        lot_tenders = root_element.findall(".//efac:NoticeResult/efac:LotTender", namespaces=self.parser.nsmap)
        for lot_tender in lot_tenders:
            tender_id = self.parser.find_text(lot_tender, "./cbc:ID", namespaces=self.parser.nsmap)
            payable_amount_element = lot_tender.find("./cac:LegalMonetaryTotal/cbc:PayableAmount", namespaces=self.parser.nsmap)
            if tender_id and payable_amount_element is not None:
                payable_amount = float(payable_amount_element.text) if payable_amount_element.text else None
                currency_id = payable_amount_element.get('currencyID')
                if payable_amount and currency_id:
                    result_id = self.parser.find_text(lot_tender.getparent(), "./efac:LotResult/cbc:ID", namespaces=self.parser.nsmap)
                    if result_id:
                        self.update_bid_value(tender_id, payable_amount, currency_id)
                        self.update_award_value(result_id, payable_amount, currency_id)

    def update_bid_value(self, bid_id, amount, currency):
        bid = next((b for b in self.tender["bids"]["details"] if b["id"] == bid_id), None)
        if bid:
            bid["value"] = {"amount": amount, "currency": currency}

    def update_award_value(self, award_id, amount, currency):
        award = next((a for a in self.awards if a['id'] == award_id), None)
        if award:
            award["value"] = {"amount": amount, "currency": currency}

    def fetch_bt735_cvd_contract_type(self, root_element):
        lot_results = root_element.findall(".//efac:NoticeResult/efac:LotResult", namespaces=self.parser.nsmap)
        for lot_result in lot_results:
            result_id = self.parser.find_text(lot_result, "./cbc:ID", namespaces=self.parser.nsmap)
            if result_id:
                cvd_contract_type = self.parser.find_text(lot_result, "./efac:StrategicProcurement/efac:StrategicProcurementInformation/efbc:ProcurementCategoryCode", namespaces=self.parser.nsmap)
                if cvd_contract_type:
                    self.add_cv_contract_type(result_id, cvd_contract_type)

    def add_cv_contract_type(self, award_id, cvd_contract_type):
        item_id = 1
        award = next((a for a in self.awards if a['id'] == award_id), None)
        if award:
            classification = {
                "scheme": "eu-cvd-contract-type",
                "id": cvd_contract_type,
                "description": self.get_contract_type_description(cvd_contract_type)
            }
            item = {
                "id": str(item_id),
                "additionalClassifications": [classification]
            }
            award.setdefault("items", []).append(item)
            item_id += 1

    def get_contract_type_description(self, code):
        descriptions = {
            "oth-serv-contr": "other service contract",
            # Add other mappings as required
        }
        return descriptions.get(code, "Unknown contract type")  

    def update_party_roles(self, org_id, roles):
        organization = self.get_or_create_organization(self.parties, org_id)
        for role in roles:
            if role not in organization['roles']:
                organization['roles'].append(role)

    def fetch_opt_300_contract_signatory(self, root_element):
        signatory_parties = root_element.findall(".//efac:NoticeResult/efac:SettledContract/cac:SignatoryParty", namespaces=self.parser.nsmap)
        for signatory_party in signatory_parties:
            signatory_id = self.parser.find_text(signatory_party, "./cac:PartyIdentification/cbc:ID", namespaces=self.parser.nsmap)
            if signatory_id:
                org = self.get_or_create_organization(self.parties, signatory_id)
                if 'buyer' not in org['roles']:
                    org['roles'].append('buyer')
                org_name = self.parser.find_text(
                    root_element, 
                    f".//efac:Organization[efac:Company/cac:PartyIdentification/cbc:ID='{signatory_id}']/efac:Company/cac:PartyName/cbc:Name", 
                    namespaces=self.parser.nsmap
                )
                if org_name:
                    org["name"] = org_name
                contract_id = self.parser.find_text(signatory_party, './../../cbc:ID', namespaces=self.parser.nsmap)
                for award in self.awards:
                    if contract_id in award.get("relatedContracts", []):
                        award.setdefault("buyers", []).append({"id": signatory_id})

    def fetch_opt_320_lotresult_tender_reference(self, root_element):
        lot_results = root_element.findall(".//efac:NoticeResult/efac:LotResult", namespaces=self.parser.nsmap)
        for lot_result in lot_results:
            lot_tender_ids = lot_result.findall("./efac:LotTender/cbc:ID", namespaces=self.parser.nsmap)
            if lot_tender_ids:
                result_id = self.parser.find_text(lot_result, "./cbc:ID", namespaces=self.parser.nsmap)
                for tender_id in lot_tender_ids:
                    if result_id and tender_id:
                        self.add_tender_id_to_award(result_id, tender_id.text)

    def add_tender_id_to_award(self, award_id, tender_id):
        award = next((a for a in self.awards if a['id'] == award_id), None)
        if award:
            if 'relatedBids' not in award:
                award['relatedBids'] = []
            if tender_id not in award['relatedBids']:
                award['relatedBids'].append(tender_id) 

    def fetch_opt_322_lotresult_technical_identifier(self, root_element):
        lot_results = root_element.findall(".//efac:NoticeResult/efac:LotResult", namespaces=self.parser.nsmap)
        for lot_result in lot_results:
            result_id = self.parser.find_text(lot_result, "./cbc:ID", namespaces=self.parser.nsmap)
            if result_id:
                self.add_or_update_award(result_id)

    def add_or_update_award(self, award_id):
        award = next((a for a in self.awards if a['id'] == award_id), None)
        if not award:
            self.awards.append({"id": award_id, "relatedLots": []})    

    def fetch_opt_315_contract_identifier(self, root_element):
        settled_contracts = root_element.findall(".//efac:SettledContract", namespaces=self.parser.nsmap)
        for contract in settled_contracts:
            contract_id = self.parser.find_text(contract, "./cbc:ID", namespaces=self.parser.nsmap)
            
            if not contract_id:
                logging.warning("Contract ID not found, skipping this contract.")
                continue

            # Default variables for potential missing fields
            issue_date = contract_signed_date = contract_reference = contract_url = revenue_buyer_amount = revenue_user_amount = eu_funds_detail = contract_title = eu_funds_programme = public_transport_distance = framework_notice_id = None
            
            # BT-145: Contract Conclusion Date
            issue_date = self.parser.find_text(contract, "./cbc:IssueDate", namespaces=self.parser.nsmap)
            contract_signed_date = datetime.fromisoformat(issue_date).isoformat() if issue_date else None

            # BT-150: Contract Identifier
            contract_reference = self.parser.find_text(contract, "./efac:ContractReference/cbc:ID", namespaces=self.parser.nsmap)

            # BT-151: Contract URL
            contract_url = self.parser.find_text(contract, "./cbc:URI", namespaces=self.parser.nsmap)

            # BT-160: Concession Revenue Buyer
            revenue_buyer_amount = self.parser.find_text(contract, "./efac:ConcessionRevenue/efbc:RevenueBuyerAmount", namespaces=self.parser.nsmap)

            # BT-162: Concession Revenue User
            revenue_user_amount = self.parser.find_text(contract, "./efac:ConcessionRevenue/efbc:RevenueUserAmount", namespaces=self.parser.nsmap)

            # BT-6110: Contract EU Funds Details
            eu_funds_detail = self.parser.find_text(contract, "./efac:Funding/cbc:Description", namespaces=self.parser.nsmap)

            # BT-721: Contract Title
            contract_title = self.parser.find_text(contract, "./cbc:Title", namespaces=self.parser.nsmap)

            # BT-722: Contract EU Funds Programme
            eu_funds_programme = self.parser.find_text(contract, "./efac:Funding/cbc:FundingProgramCode", namespaces=self.parser.nsmap)

            # OPP-080: Kilometers Public Transport
            public_transport_distance = self.parser.find_text(contract, "./efbc:PublicTransportationCumulatedDistance", namespaces=self.parser.nsmap)

            # OPT-100: Framework Notice Identifier
            framework_notice_id = self.parser.find_text(contract, "./cac:NoticeDocumentReference/cbc:ID", namespaces=self.parser.nsmap)

            contract_info = {
                "id": contract_id,
                "dateSigned": contract_signed_date,
                "title": contract_title,
                "documents": [{
                    "id": str(uuid.uuid4()),
                    "url": contract_url,
                    "documentType": "contractSigned"
                }] if contract_url else [],
                "identifiers": [{
                    "id": contract_reference,
                    "scheme": "FR-SCN DEF"
                }] if contract_reference else [],
                "finance": [{
                    "description": eu_funds_detail,
                    "title": eu_funds_programme
                }] if eu_funds_detail or eu_funds_programme else [],
                "publicPassengerTransportServicesKilometers": int(public_transport_distance) if public_transport_distance else None,
                "relatedBids": ["TEN-0001"]  # Example, adjust as needed
            }

            if framework_notice_id:
                contract_info.setdefault("relatedProcesses", []).append({
                    "id": str(uuid.uuid4()),
                    "relationship": ["framework"],
                    "identifier": framework_notice_id,
                    "scheme": "internal"
                })

            lot_results = contract.xpath("ancestor::efac:NoticeResult/efac:LotResult[efac:SettledContract/cbc:ID='" + contract_id + "']", namespaces=self.parser.nsmap)
            for lot_result in lot_results:
                result_id = self.parser.find_text(lot_result, "./cbc:ID", namespaces=self.parser.nsmap)
                if result_id:
                    self.add_or_update_contract(result_id, contract_info)

    def add_or_update_contract(self, result_id, contract_info):
        found = False
        if not self.awards:
            self.awards.append({"id": result_id, "contracts": []})
            
        for award in self.awards:
            if award["id"] == result_id:
                if "contracts" not in award:
                    award["contracts"] = []

                # Check for existing contract
                for contract in award["contracts"]:
                    if contract["id"] == contract_info["id"]:
                        contract.update(contract_info)
                        found = True
                        break

                if not found:
                    award["contracts"].append(contract_info)
                return
        
        # If no existing award with result_id, create new award
        new_award = {
            "id": result_id,
            "contracts": [contract_info]
        }
        self.awards.append(new_award)
    
    def fetch_bt200_contract_modification(self, root_element):
        contract_mods = root_element.findall(".//efac:ContractModification", namespaces=self.parser.nsmap)
        for mod in contract_mods:
            contract_id = self.parser.find_text(mod, ".//efac:Change/efac:ChangedSection/efbc:ChangeSectionIdentifier", namespaces=self.parser.nsmap)
            reason_codes = mod.findall(".//efac:ChangeReason/cbc:ReasonCode", namespaces=self.parser.nsmap)
            reason_descriptions = mod.findall(".//efac:ChangeReason/efbc:ReasonDescription", namespaces=self.parser.nsmap)
            change_descriptions = mod.findall(".//efac:Change/efbc:ChangeDescription", namespaces=self.parser.nsmap)
            
            if contract_id:
                contract = self.get_or_create_contract(contract_id)
                for idx, reason_code in enumerate(reason_codes):
                    amendment_id = str(uuid.uuid4())
                    amendment = {
                        "id": amendment_id,
                        "rationaleClassifications": [{
                            "id": reason_code.text,
                            "description": self.get_modification_reason_description(reason_code.text),
                            "scheme": "modification justification"
                        }],
                        "rationale": reason_descriptions[idx].text if idx < len(reason_descriptions) else None,
                        "description": change_descriptions[idx].text if idx < len(change_descriptions) else None
                    }
                    contract.setdefault("amendments", []).append(amendment)
    
    def get_modification_reason_description(self, code):
        reason_descriptions = {
            "add-wss": "Need for additional works, services or supplies by the original contractor.",
            # More values as needed
        }
        return reason_descriptions.get(code, "Unknown modification reason")

    def get_or_create_contract(self, contract_id):
        for award in self.awards:
            for contract in award.get("contracts", []):
                if contract["id"] == contract_id:
                    return contract
        new_contract = {
            "id": contract_id,
            "awardID": None  # This will be set later during lot result processing
        }
        if not self.awards:
            self.awards.append({"id": str(uuid.uuid4()), "contracts": [new_contract]})
        else:
            self.awards[0]["contracts"].append(new_contract)
        return new_contract

    def fetch_bt775_social_procurement(self, root_element):
        lots = root_element.xpath(".//cac:ProcurementProjectLot[cbc:ID/@schemeName='Lot']", namespaces=self.parser.nsmap)
        for lot in lots:
            codes = lot.xpath(".//cac:ProcurementProject/cac:ProcurementAdditionalType[cbc:ProcurementTypeCode/@listName='social-objective']/cbc:ProcurementTypeCode", namespaces=self.parser.nsmap)
            lot_id = self.parser.find_text(lot, "./cbc:ID", namespaces=self.parser.nsmap)
            sustainability = []
            strategies = ["awardCriteria", "contractPerformanceConditions", "selectionCriteria", "technicalSpecifications"]
            for code in codes:
                code = code.text
                if code and code != "none":
                    sustainability.append({
                        "goal": self.map_social_procurement_code(code),
                        "strategies": strategies
                    })
            if sustainability:
                lot_info = {
                    "id": lot_id,
                    "hasSustainability": True,
                    "sustainability": sustainability
                }
                self.add_or_update_lot(self.tender["lots"], lot_info)

    def map_social_procurement_code(self, code):
        mapping = {
            "et-eq": "social.ethnicEquality",
            # Add more mappings as required
        }
        return mapping.get(code, code)
    
    def fetch_bt06_lot_strategic_procurement(self, root_element):
        lots = root_element.xpath(".//cac:ProcurementProjectLot[cbc:ID/@schemeName='Lot']", namespaces=self.parser.nsmap)
        for lot in lots:
            codes = lot.xpath(".//cac:ProcurementProject/cac:ProcurementAdditionalType[cbc:ProcurementTypeCode/@listName='strategic-procurement']/cbc:ProcurementTypeCode", namespaces=self.parser.nsmap)
            lot_id = self.parser.find_text(lot, "./cbc:ID", namespaces=self.parser.nsmap)
            sustainability = []
            strategies = ["awardCriteria", "contractPerformanceConditions", "selectionCriteria", "technicalSpecifications"]
            for code in codes:
                code = code.text
                if code and code != "none":
                    sustainability.append({
                        "goal": self.map_strategic_procurement_code(code),
                        "strategies": strategies
                    })
            if sustainability:
                lot_info = {
                    "id": lot_id,
                    "hasSustainability": True,
                    "sustainability": sustainability
                }
                self.add_or_update_lot(self.tender["lots"], lot_info)

    def map_strategic_procurement_code(self, code):
        mapping = {
            "inn-pur": "economic.innovativePurchase",
            # Add more mappings as required
        }
        return mapping.get(code, code)
    
    def fetch_bt539_award_criterion_type(self, root_element):
        lots = root_element.xpath(".//cac:ProcurementProjectLot[cbc:ID/@schemeName='Lot']", namespaces=self.parser.nsmap)
        for lot in lots:
            criteria_elements = lot.xpath(".//cac:TenderingTerms/cac:AwardingTerms/cac:AwardingCriterion/cac:SubordinateAwardingCriterion", namespaces=self.parser.nsmap)
            lot_id = self.parser.find_text(lot, "./cbc:ID", namespaces=self.parser.nsmap)
            for criterion in criteria_elements:
                criterion_type = self.parser.find_text(criterion, "./cbc:AwardingCriterionTypeCode[@listName='award-criterion-type']")
                if criterion_type:
                    lot_info = {
                        "id": lot_id,
                        "awardCriteria": {
                            "criteria": [{"type": criterion_type}]
                        }
                    }
                    self.add_or_update_lot(self.tender["lots"], lot_info)
    
    def fetch_bt540_award_criterion_description(self, root_element):
        lots = root_element.xpath(".//cac:ProcurementProjectLot[cbc:ID/@schemeName='Lot']", namespaces=self.parser.nsmap)
        for lot in lots:
            criteria_elements = lot.xpath(".//cac:TenderingTerms/cac:AwardingTerms/cac:AwardingCriterion/cac:SubordinateAwardingCriterion", namespaces=self.parser.nsmap)
            lot_id = self.parser.find_text(lot, "./cbc:ID", namespaces=self.parser.nsmap)
            for criterion in criteria_elements:
                description = self.parser.find_text(criterion, "./cbc:Description")
                if description:
                    lot_info = {
                        "id": lot_id,
                        "awardCriteria": {
                            "criteria": [{"description": description}]
                        }
                    }
                    self.add_or_update_lot(self.tender["lots"], lot_info)

    def fetch_bt541_award_criterion_fixed_number(self, root_element):
        lots = root_element.xpath(".//cac:ProcurementProjectLot[cbc:ID/@schemeName='Lot']", namespaces=self.parser.nsmap)
        for lot in lots:
            criteria_elements = lot.xpath(".//cac:TenderingTerms/cac:AwardingTerms/cac:AwardingCriterion/cac:SubordinateAwardingCriterion/ext:UBLExtensions/ext:UBLExtension/ext:ExtensionContent/efext:EformsExtension/efac:AwardCriterionParameter[efbc:ParameterCode/@listName='number-fixed']/efbc:ParameterNumeric", namespaces=self.parser.nsmap)
            lot_id = self.parser.find_text(lot, "./cbc:ID", namespaces=self.parser.nsmap)
            for criterion in criteria_elements:
                number = self.parser.find_text(criterion, "./efbc:ParameterNumeric")
                if number:
                    lot_info = {
                        "id": lot_id,
                        "awardCriteria": {
                            "criteria": [{"numbers": [{"number": float(number)}]}]
                        }
                    }
                    self.add_or_update_lot(self.tender["lots"], lot_info)
    
    def fetch_bt5421_award_criterion_number_weight(self, root_element):
        lots = root_element.xpath(".//cac:ProcurementProjectLot[cbc:ID/@schemeName='Lot']", namespaces=self.parser.nsmap)
        for lot in lots:
            criteria_elements = lot.xpath(".//cac:TenderingTerms/cac:AwardingTerms/cac:AwardingCriterion/cac:SubordinateAwardingCriterion/ext:UBLExtensions/ext:UBLExtension/ext:ExtensionContent/efext:EformsExtension/efac:AwardCriterionParameter[efbc:ParameterCode/@listName='number-weight']/efbc:ParameterCode", namespaces=self.parser.nsmap)
            lot_id = self.parser.find_text(lot, "./cbc:ID", namespaces=self.parser.nsmap)
            for criterion in criteria_elements:
                weight = self.parser.find_text(criterion, "./efbc:ParameterCode")
                if weight:
                    lot_info = {
                        "id": lot_id,
                        "awardCriteria": {
                            "criteria": [{"numbers": [{"weight": self.map_award_criterion_number_weight(weight)}]}]
                        }
                    }
                    self.add_or_update_lot(self.tender["lots"], lot_info)

    def fetch_bt5422_award_criterion_number_fixed(self, root_element):
        lots = root_element.xpath(".//cac:ProcurementProjectLot[cbc:ID/@schemeName='Lot']", namespaces=self.parser.nsmap)
        for lot in lots:
            criteria_elements = lot.xpath(".//cac:TenderingTerms/cac:AwardingTerms/cac:AwardingCriterion/cac:SubordinateAwardingCriterion/ext:UBLExtensions/ext:UBLExtension/ext:ExtensionContent/efext:EformsExtension/efac:AwardCriterionParameter[efbc:ParameterCode/@listName='number-fixed']/efbc:ParameterCode", namespaces=self.parser.nsmap)
            lot_id = self.parser.find_text(lot, "./cbc:ID", namespaces=self.parser.nsmap)
            for criterion in criteria_elements:
                fixed = self.parser.find_text(criterion, "./efbc:ParameterCode")
                if fixed:
                    lot_info = {
                        "id": lot_id,
                        "awardCriteria": {
                            "criteria": [{"numbers": [{"fixed": self.map_award_criterion_number_fixed(fixed)}]}]
                        }
                    }
                    self.add_or_update_lot(self.tender["lots"], lot_info)

    def fetch_bt5423_award_criterion_number_threshold(self, root_element):
        lots = root_element.xpath(".//cac:ProcurementProjectLot[cbc:ID/@schemeName='Lot']", namespaces=self.parser.nsmap)
        for lot in lots:
            criteria_elements = lot.xpath(".//cac:TenderingTerms/cac:AwardingTerms/cac:AwardingCriterion/cac:SubordinateAwardingCriterion/ext:UBLExtensions/ext:UBLExtension/ext:ExtensionContent/efext:EformsExtension/efac:AwardCriterionParameter[efbc:ParameterCode/@listName='number-threshold']/efbc:ParameterCode", namespaces=self.parser.nsmap)
            lot_id = self.parser.find_text(lot, "./cbc:ID", namespaces=self.parser.nsmap)
            for criterion in criteria_elements:
                threshold = self.parser.find_text(criterion, "./efbc:ParameterCode")
                if threshold:
                    lot_info = {
                        "id": lot_id,
                        "awardCriteria": {
                            "criteria": [{"numbers": [{"threshold": self.map_award_criterion_number_threshold(threshold)}]}]
                        }
                    }
                    self.add_or_update_lot(self.tender["lots"], lot_info)

    def fetch_bt543_award_criteria_complicated(self, root_element):
        lots = root_element.xpath(".//cac:ProcurementProjectLot[cbc:ID/@schemeName='Lot']", namespaces=self.parser.nsmap)
        for lot in lots:
            calculation_expression = self.parser.find_text(lot, ".//cac:TenderingTerms/cac:AwardingTerms/cac:AwardingCriterion/cbc:CalculationExpression")
            lot_id = self.parser.find_text(lot, "./cbc:ID", namespaces=self.parser.nsmap)
            if calculation_expression:
                lot_info = {
                    "id": lot_id,
                    "awardCriteria": {
                        "weightingDescription": calculation_expression
                    }
                }
                self.add_or_update_lot(self.tender["lots"], lot_info)

    def fetch_bt733_award_criteria_order_rationale(self, root_element):
        lots = root_element.xpath(".//cac:ProcurementProjectLot[cbc:ID/@schemeName='Lot']", namespaces=self.parser.nsmap)
        for lot in lots:
            order_rationale = self.parser.find_text(lot, ".//cac:TenderingTerms/cac:AwardingTerms/cac:AwardingCriterion/cbc:Description")
            lot_id = self.parser.find_text(lot, "./cbc:ID", namespaces=self.parser.nsmap)
            if order_rationale:
                lot_info = {
                    "id": lot_id,
                    "awardCriteria": {
                        "orderRationale": order_rationale
                    }
                }
                self.add_or_update_lot(self.tender["lots"], lot_info)

    def fetch_bt734_award_criterion_name(self, root_element):
        lots = root_element.xpath(".//cac:ProcurementProjectLot[cbc:ID/@schemeName='Lot']", namespaces=self.parser.nsmap)
        for lot in lots:
            criteria_elements = lot.xpath(".//cac:TenderingTerms/cac:AwardingTerms/cac:AwardingCriterion/cac:SubordinateAwardingCriterion", namespaces=self.parser.nsmap)
            lot_id = self.parser.find_text(lot, "./cbc:ID", namespaces=self.parser.nsmap)
            for criterion in criteria_elements:
                name = self.parser.find_text(criterion, "./cbc:Name")
                if name:
                    lot_info = {
                        "id": lot_id,
                        "awardCriteria": {
                            "criteria": [{"name": name}]
                        }
                    }
                    self.add_or_update_lot(self.tender["lots"], lot_info)

    def fetch_bt773_subcontracting(self, root_element):
        """
        Fetches BT-773: Whether at least a part of the contract will be subcontracted.
        """
        lot_tenders = root_element.xpath(".//efac:NoticeResult/efac:LotTender", namespaces=self.parser.nsmap)
        for lot_tender in lot_tenders:
            tender_id = self.parser.find_text(lot_tender, "./cbc:ID", namespaces=self.parser.nsmap)
                    
            if tender_id:
                bid = {
                    "id": tender_id,
                    "relatedLots": [self.parser.find_text(lot_tender, "./efac:TenderLot/cbc:ID")]
                }

                subcontracting_term = self.parser.find_text(
                    lot_tender, "./efac:SubcontractingTerm[efbc:TermCode/@listName='applicability']/efbc:TermCode", namespaces=self.parser.nsmap
                )
                if subcontracting_term:
                    bid["hasSubcontracting"] = subcontracting_term.lower() == "yes"

                # Add rank
                rank = self.parser.find_text(lot_tender, "./cbc:RankCode", namespaces=self.parser.nsmap)
                if rank:
                    bid["rank"] = int(rank)
                    bid["hasRank"] = True

                # Add "value"
                value = self.parser.find_text(lot_tender, "./cac:LegalMonetaryTotal/cbc:PayableAmount", namespaces=self.parser.nsmap)
                currency_id = self.parser.find_attribute(lot_tender, "./cac:LegalMonetaryTotal/cbc:PayableAmount", "currencyID")
                if value and currency_id:
                    bid["value"] = {
                        "amount": float(value),
                        "currency": currency_id
                    }

                # Find tenderer organizations
                tenderers = lot_tender.xpath("efac:TenderingParty[efac:Tenderer]", namespaces=self.parser.nsmap)
                for tenderer_entry in tenderers:
                    tenderer_id = self.parser.find_text(tenderer_entry, "efac:Tenderer/efac:PartyIdentification/cbc:ID", namespaces=self.parser.nsmap)
                    if tenderer_id:
                        bid.setdefault("tenderers", []).append({
                            "id": tenderer_id
                        })

                self.tender["bids"]["details"].append(bid)

    def fetch_opt_310_tendering_party_id(self, root_element):
        tender_detail_mapping = {}
        notice_results = root_element.xpath(".//efac:NoticeResult", namespaces=self.parser.nsmap)
        for notice_result in notice_results:
            lot_tenders = notice_result.xpath(".//efac:LotTender", namespaces=self.parser.nsmap)
            for lot_tender in lot_tenders:
                tender_id = self.parser.find_text(lot_tender, "cbc:ID")
                tendering_party_id = self.parser.find_text(lot_tender, "efac:TenderingParty/cbc:ID")
                if tender_id and tendering_party_id:
                    tender_detail_mapping[tender_id] = tendering_party_id

        for tender_id, tendering_party_id in tender_detail_mapping.items():
            tendering_party = self.parser.find_node(root_element, f".//efac:TenderingParty[cbc:ID='{tendering_party_id}']", namespaces=self.parser.nsmap)
            tenderers = tendering_party.findall(".//efac:Tenderer", namespaces=self.parser.nsmap)

            for tenderer in tenderers:
                tenderer_id = self.parser.find_text(tenderer, "cbc:ID")
                if tenderer_id:
                    self.add_or_update_party(self.parties, {
                        "id": tenderer_id,
                        "roles": ["tenderer"]
                    })
                    self.add_or_update_bid_tenderers(tender_id, tenderer_id)

    def add_or_update_bid_tenderers(self, bid_id, tenderer_id):
        bid = next((b for b in self.tender["bids"]["details"] if b["id"] == bid_id), None)
        if bid:
            bid.setdefault("tenderers", []).append({"id": tenderer_id})
        else:
            self.tender["bids"]["details"].append({
                "id": bid_id,
                "tenderers": [{"id": tenderer_id}]
            })

    def fetch_opt_301_tenderer_maincont(self, root_element):
        notice_results = root_element.findall(".//efac:NoticeResult", namespaces=self.parser.nsmap)
        for notice_result in notice_results:
            lot_tenders = notice_result.findall(".//efac:LotTender", namespaces=self.parser.nsmap)
            for lot_tender in lot_tenders:
                tender_id = self.parser.find_text(lot_tender, "./cbc:ID", namespaces=self.parser.nsmap)
                subcontractors = lot_tender.findall(".//efac:SubContractor", namespaces=self.parser.nsmap)
                for subcontractor in subcontractors:
                    subcontractor_id = self.parser.find_text(subcontractor, "./cbc:ID", namespaces=self.parser.nsmap)
                    main_contractors = subcontractor.findall(".//efac:MainContractor", namespaces=self.parser.nsmap)
                    for main_contractor in main_contractors:
                        main_contractor_id = self.parser.find_text(main_contractor, "./cbc:ID", namespaces=self.parser.nsmap)

                        if main_contractor_id:
                            main_contractor_org = next((o for o in self.parties if o['id'] == main_contractor_id), None)
                            if not main_contractor_org:
                                main_contractor_org = {
                                    "id": main_contractor_id,
                                    "roles": ["tenderer"]
                                }
                                self.parties.append(main_contractor_org)
                            else:
                                if "tenderer" not in main_contractor_org.get('roles', []):
                                    main_contractor_org['roles'].append("tenderer")

                        bid = next((b for b in self.tender["bids"]["details"] if b['id'] == tender_id), None)
                        if not bid:
                            bid = {
                                "id": tender_id,
                                "subcontracting": {
                                    "subcontracts": []
                                }
                            }
                            self.tender["bids"]["details"].append(bid)

                        subcontract = next((s for s in bid["subcontracting"]["subcontracts"]
                                            if s["subcontractor"]["id"] == subcontractor_id), None)
                        if not subcontract:
                            subcontract = {
                                "id": str(len(bid["subcontracting"]["subcontracts"]) + 1),
                                "subcontractor": {
                                    "id": subcontractor_id
                                },
                                "mainContractors": []
                            }
                            bid["subcontracting"]["subcontracts"].append(subcontract)

                        main_contractor_references = {
                            "id": main_contractor_id
                        }
                        subcontract["mainContractors"].append(main_contractor_references)
    def fetch_opt_320_contract_tender_reference(self, root_element):
        settled_contracts = root_element.findall(".//efac:NoticeResult/efac:SettledContract", namespaces=self.parser.nsmap)
        for contract in settled_contracts:
            tender_id = self.parser.find_text(contract, "./efac:LotTender/cbc:ID", namespaces=self.parser.nsmap)
            contract_id = self.parser.find_text(contract, "./cbc:ID", namespaces=self.parser.nsmap)
            if tender_id and contract_id:
                self.add_or_update_contract_related_bids(contract_id, tender_id)
                self.handle_tendering_party(contract_id, tender_id)

    def handle_tendering_party(self, contract_id, tender_id):
        root = self.parser.root
        tendering_party_id = self.parser.find_text(root, f".//efac:LotTender[cbc:ID='{tender_id}']/efac:TenderingParty/cbc:ID", namespaces=self.parser.nsmap)
        if tendering_party_id:
            tenderers = root.findall(f".//efac:TenderingParty[cbc:ID='{tendering_party_id}']/*/efac:Tenderer", namespaces=self.parser.nsmap)
            for tenderer in tenderers:
                tenderer_id = self.parser.find_text(tenderer, "./cbc:ID", namespaces=self.parser.nsmap)
                if tenderer_id:
                    self.update_party_roles(tenderer_id, ["supplier"])
                    self.add_supplier_to_award(contract_id, tenderer_id)

    def fetch_bt746_organization_listed_market(self, root_element):
        organizations = root_element.findall(".//efac:Organizations/efac:Organization", namespaces=self.parser.nsmap)
        for org_element in organizations:
            org_id = self.parser.find_text(org_element, "./efac:Company/cac:PartyIdentification/cbc:ID[@schemeName='organization']", namespaces=self.parser.nsmap)
            if org_id:
                listed_indicator_text = self.parser.find_text(org_element, "./efbc:ListedOnRegulatedMarketIndicator", namespaces=self.parser.nsmap)
                if listed_indicator_text is not None:
                    listed_indicator = listed_indicator_text.lower() == 'true'
                    organization = self.get_or_create_organization(self.parties, org_id)
                    organization.setdefault("details", {})["listedOnRegulatedMarket"] = listed_indicator
                    self.add_or_update_party(self.parties, organization)

    def fetch_bt165_company_size(self, root_element):
        organizations = root_element.findall(".//efac:Organizations/efac:Organization", namespaces=self.parser.nsmap)
        for org_element in organizations:
            org_id = self.parser.find_text(org_element, "./efac:Company/cac:PartyIdentification/cbc:ID[@schemeName='organization']", namespaces=self.parser.nsmap)
            if org_id:
                size_code = self.parser.find_text(org_element, "./efac:Company/efbc:CompanySizeCode", namespaces=self.parser.nsmap)
                if size_code:
                    organization = self.get_or_create_organization(self.parties, org_id)
                    organization.setdefault("details", {})["scale"] = size_code.lower()

    def fetch_bt633_natural_person_indicator(self, root_element):
        organizations = root_element.findall(".//efac:Organizations/efac:Organization", namespaces=self.parser.nsmap)
        for org_element in organizations:
            org_id = self.parser.find_text(org_element, "./efac:Company/cac:PartyIdentification/cbc:ID[@schemeName='organization']", namespaces=self.parser.nsmap)
            if org_id:
                natural_person_indicator = self.parser.find_text(org_element, "./efbc:NaturalPersonIndicator", namespaces=self.parser.nsmap)
                if natural_person_indicator is not None:
                    if natural_person_indicator.lower() == 'true':
                        # Set to selfEmployed if the indicator is true
                        organization = self.get_or_create_organization(self.parties, org_id)
                        organization.setdefault("details", {})["scale"] = "selfEmployed"      

    def gather_party_info(self, root_element):
        logger = logging.getLogger(__name__)
        parties = []

    def add_or_update_party(self, parties, new_party):
        existing_party = next((p for p in parties if p['id'] == new_party['id']), None)
        if existing_party:
            for key, value in new_party.items():
                if key == 'roles':
                    existing_party['roles'] = list(set(existing_party.get('roles', []) + value))
                elif isinstance(value, list):
                    existing_party.setdefault(key, []).extend(value)
                elif isinstance(value, dict):
                    existing_party.setdefault(key, {}).update(value)
                else:
                    existing_party[key] = value
        else:
            parties.append(new_party)

    def convert_tender_to_ocds(self):
        root = self.parser.root

        ocid = "blah"  # Replace with actual OCID if available
        dispatch_datetime = self.get_dispatch_date_time()
        tender_title = self.parser.find_text(root, ".//cac:ProcurementProject/cbc:Name")

        form_type = self.get_form_type(root)
        language = self.fetch_notice_language(root)

        self.tender.setdefault("bids", {}).setdefault("details", [])

        try:
            # Fetch various data elements
            self.fetch_bt710_bt711_bid_statistics(root)
            self.fetch_bt712_complaints_statistics(root)
            self.fetch_bt09_cross_border_law(root)
            self.fetch_bt111_lot_buyer_categories(root)
            self.fetch_bt766_dynamic_purchasing_system_lot(root)
            self.fetch_bt766_dynamic_purchasing_system_part(root)
            self.fetch_bt775_social_procurement(root)
            self.fetch_bt06_lot_strategic_procurement(root)
            self.fetch_bt539_award_criterion_type(root)
            self.fetch_bt540_award_criterion_description(root)
            self.fetch_bt541_award_criterion_fixed_number(root)
            self.fetch_bt5421_award_criterion_number_weight(root)
            self.fetch_bt5422_award_criterion_number_fixed(root)
            self.fetch_bt5423_award_criterion_number_threshold(root)
            self.fetch_bt543_award_criteria_complicated(root)
            self.fetch_bt733_award_criteria_order_rationale(root)
            self.fetch_bt734_award_criterion_name(root)
            self.handle_bt14_and_bt707(root)
            self.fetch_opp_050_buyers_group_lead(root)
            self.fetch_opt_300_contract_signatory(root)
            self.fetch_opt_301_tenderer_maincont(root)
            self.fetch_bt773_subcontracting(root)
            self.fetch_opt_310_tendering_party_id(root)
            self.fetch_opt_320_contract_tender_reference(root)
            self.fetch_bt746_organization_listed_market(root)
            self.fetch_bt165_company_size(root)
            self.fetch_bt633_natural_person_indicator(root)
            self.fetch_bt47_participants(root)
            self.fetch_bt5010_lot_financing(root)
            self.fetch_bt5011_contract_financing(root)
            self.fetch_bt508_buyer_profile(root)
            self.fetch_bt60_lot_funding(root)
            self.fetch_bt610_activity_entity(root)
            self.fetch_bt740_contracting_entity(root)
            self.fetch_opp_051_awarding_cpb_buyer(root)
            self.fetch_opp_052_acquiring_cpb_buyer(root)
            self.fetch_opt_030_service_type(root)
            self.fetch_opt_170_tender_leader(root)
            self.fetch_opt_301_lot_mediator(root)
            self.fetch_opt_301_lot_review_org(root)
            self.fetch_opt_301_part_review_org(root)
            self.fetch_opt_300_buyer_technical_reference(root)
            self.fetch_opt_301_add_info_provider(root)
            self.fetch_opt_301_lot_employ_legis(root)
            self.fetch_opt_301_lot_environ_legis(root)
            self.fetch_opt_322_lotresult_technical_identifier(root)
            self.fetch_bt144_not_awarded_reason(root)
            self.fetch_bt1451_winner_decision_date(root)
            self.fetch_bt163_concession_value_description(root)
            self.fetch_bt660_framework_re_estimated_value(root)
            self.fetch_bt709_framework_maximum_value(root)
            self.fetch_bt720_tender_value(root)
            self.fetch_bt735_cvd_contract_type(root)
        except Exception as e:
            logging.error(f"Error fetching data: {e}")

        try:
            # Process other relevant data
            activities = self.parse_activity_authority(root)
            legal_types = self.parse_buyer_legal_type(root)
            lots = self.parse_lots(root)
            legal_basis = self.get_legal_basis(root)
            additional_info = self.fetch_bt300_additional_info(root)
            tender_estimated_value = self.fetch_tender_estimated_value(root)
            procedure_type = self.parse_procedure_type(root)
            procurement_method_rationale, procurement_method_rationale_classifications = self.parse_direct_award_justification(root)
            procedure_features = self.parse_procedure_features(root)
            items = self.parse_classifications(root)
            related_processes = self.parse_related_processes(root)

            self.handle_bidding_documents(root)
            self.fetch_opt_315_contract_identifier(root)
            self.fetch_bt200_contract_modification(root)

            # Gather party information
            self.parties = self.fetch_bt500_company_organization(root)
        except Exception as e:
            logging.error(f"Error processing data: {e}")

        tenders_lots_items = []
        for lot in lots:
            lot_id = lot.get("id")
            for item in items:
                if item.get("relatedLot") == lot_id:
                    tenders_lots_items.append({
                        "relatedLot": lot_id,
                        **item
                    })

        awards = []
        for award in self.awards:
            award_id = award.get("id")
            award_contracts = [contract for contract in self.get_contracts() if award_id in contract.get("relatedBids", [])]
            awards.append({
                **award,
                "contracts": award_contracts
            })

        release = {
            "id": ocid,
            "ocid": ocid,
            "date": dispatch_datetime,
            "initiationType": "tender",
            "tag": form_type['tag'],
            "language": language,
            "parties": self.parties,
            "tender": {
                "id": self.parser.find_text(root, ".//cbc:ContractFolderID"),
                "status": form_type.get('tender_status', 'planned'),
                "title": tender_title,
                "description": additional_info,
                "legalBasis": legal_basis,
                "lots": lots,
                "items": tenders_lots_items,
                "value": tender_estimated_value,
                "submissionMethod": ["electronicSubmission"],
                "procurementMethod": procedure_type["method"] if procedure_type else None,
                "procurementMethodDetails": procedure_type["details"] if procedure_type else None,
                "procurementMethodRationale": procurement_method_rationale,
                "procurementMethodRationaleClassifications": procurement_method_rationale_classifications,
                "classification": {"activities": activities} if activities else None,
                "contractPeriod": self.parse_contract_period(root),
                "procedureFeatures": procedure_features if procedure_features else None,
            },
            "relatedProcesses": related_processes,
            "awards": awards,
            "contracts": [contract for contract in self.get_contracts() if 'dateSigned' in contract],
            "bids": self.tender["bids"]
        }

        cleaned_release = self.clean_release_structure(release)
        logging.info('Conversion to OCDS format completed.')
        return cleaned_release

def main(xml_file):
    logging.basicConfig(level=logging.DEBUG)
    
    try:
        parser = XMLParser(xml_file)
        converter = TEDtoOCDSConverter(parser)
        
        release_info = converter.convert_tender_to_ocds()
        
        #result = json.dumps({"releases": [release_info]}, indent=2, ensure_ascii=False)
        result = json.dumps(release_info, indent=2, ensure_ascii=False)
        print(result)
        
    except Exception as e:
        logging.error(f"An error occurred: {e}")

if __name__ == "__main__":
    xml_file = "can_24_minimal.xml"  
    main(xml_file)

