import logging
import uuid
import json
from lxml import etree
from datetime import datetime
import re

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
            "lotGroups": []
        }
        self.budget_finances = []
        logging.info('TEDtoOCDSConverter initialized with mapping.')

    def fetch_bt3202_to_ocds(self, root_element):
        results = root_element.findall(".//efac:SettledContract/efac:LotTender/cbc:ID", namespaces=self.parser.nsmap)
        for result in results:
            contract_id = result.text
            related_bids = root_element.xpath(
                f".//efac:NoticeResult/efac:LotTender[cbc:ID='{contract_id}']", namespaces=self.parser.nsmap
            )
            for bid in related_bids:
                bid_id = self.parser.find_text(bid, "./cbc:ID", namespaces=self.parser.nsmap)
                if bid_id:
                    if not self.awards:
                        self.awards.append({
                            "id": contract_id,
                            "relatedBids": [bid_id]
                        })
                    else:
                        for award in self.awards:
                            if award.get('id') == contract_id:
                                award.get('relatedBids', []).append(bid_id)
                                break
                        else:
                            self.awards.append({
                                "id": contract_id,
                                "relatedBids": [bid_id]
                            })

            for result in root_element.findall(f".//efac:LotResult[efac:SettledContract/cbc:ID='{contract_id}']", namespaces=self.parser.nsmap):
                result_id = self.parser.find_text(result, './cbc:ID', namespaces=self.parser.nsmap)
                award = next((x for x in self.awards if x['id'] == result_id), None)
                if not award:
                    continue

                lot_result = result
                tendering_party_ids = lot_result.xpath(
                    ".//efac:TenderingParty[efac:Tenderer/cbc:ID]", namespaces=self.parser.nsmap
                )

                for org_id in tendering_party_ids:
                    org_id = self.parser.find_text(org_id, "./efac:Tenderer/cbc:ID", namespaces=self.parser.nsmap)
                    organization = next((x for x in self.parties if x['id'] == org_id), None)
                    if not organization:
                        organization = {
                            "id": org_id,
                            "roles": ["supplier"]
                        }
                        self.parties.append(organization)
                    else:
                        if "supplier" not in organization.get('roles', []):
                            organization['roles'].append("supplier")

                    if "suppliers" not in award:
                        award["suppliers"] = []
                    award["suppliers"].append({
                        "id": org_id
                    })

    def fetch_bt47_participants(self, root_element):
        lots = root_element.findall(".//cac:ProcurementProjectLot", namespaces=self.parser.nsmap)
        for lot in lots:
            lot_id = self.parser.find_text(lot, "./cbc:ID", namespaces=self.parser.nsmap)
            participants = lot.findall(".//cac:PreSelectedParty", namespaces=self.parser.nsmap)
            for participant in participants:
                party_name = self.parser.find_text(participant, "./cac:PartyName/cbc:Name", namespaces=self.parser.nsmap)
                party_id = str(uuid.uuid4())

                self.parties.append({
                    "id": party_id,
                    "name": party_name,
                    "roles": ["selectedParticipant"]
                })
                for lot_item in lots:
                    lot_id = self.parser.find_text(lot_item, "./cbc:ID", namespaces=self.parser.nsmap)
                    for tender_lot in root_element.findall(".//efac:TenderLot", namespaces=self.parser.nsmap):
                        tender_id = self.parser.find_text(tender_lot, "./cbc:ID", namespaces=self.parser.nsmap)
                        if tender_id == lot_id:
                            lot_item.setdefault("designContest", {}).setdefault("selectedParticipants", []).append({
                                "id": party_id,
                                "name": party_name
                            })

    def fetch_bt5010_lot_financing(self, root_element):
        funders = []
        lots = root_element.findall(".//cac:ProcurementProjectLot", namespaces=self.parser.nsmap)
        for lot in lots:
            lot_id = self.parser.find_text(lot, "./cbc:ID", namespaces=self.parser.nsmap)
            fundings = lot.findall(".//efac:Funding", namespaces=self.parser.nsmap)
            for funding in fundings:
                financing_id = self.parser.find_text(funding, "./efbc:FinancingIdentifier", namespaces=self.parser.nsmap)
                funders.append(financing_id)

        for financing in funders:
            eu_funder = next((x for x in self.parties if x['name'] == "European Union"), None)
            if not eu_funder:
                eu_funder = {
                    "id": str(uuid.uuid4()),
                    "name": "European Union",
                    "roles": ["funder"]
                }
                self.parties.append(eu_funder)

            finance_object = {
                "id": financing,
                "relatedLots": [
                    {
                        "id": financing
                    }
                ],
                "financingParty": {
                    "id": eu_funder['id'],
                    "name": eu_funder['name']
                }
            }
            self.budget_finances.append(finance_object)
        return {}

    def fetch_bt5011_contract_financing(self, root_element):
        funders = []
        contracts = root_element.findall(".//efac:SettledContract", namespaces=self.parser.nsmap)
        for contract in contracts:
            contract_id = self.parser.find_text(contract, "./cbc:ID", namespaces=self.parser.nsmap)
            fundings = contract.findall(".//efac:Funding", namespaces=self.parser.nsmap)
            for funding in fundings:
                financing_id = self.parser.find_text(funding, "./efbc:FinancingIdentifier", namespaces=self.parser.nsmap)
                funders.append(financing_id)

        for financing in funders:
            eu_funder = next((x for x in self.parties if x['name'] == "European Union"), None)
            if not eu_funder:
                eu_funder = {
                    "id": str(uuid.uuid4()),
                    "name": "European Union",
                    "roles": ["funder"]
                }
                self.parties.append(eu_funder)

            finance_object = {
                "id": financing,
                "relatedLots": [
                    {
                        "id": financing
                    }
                ],
                "financingParty": {
                    "id": eu_funder['id'],
                    "name": eu_funder['name']
                }
            }
            self.budget_finances.append(finance_object)
        return {}

    def fetch_bt508_buyer_profile(self, root_element):
        buyers = []
        profiles = root_element.findall(".//cac:ContractingParty", namespaces=self.parser.nsmap)
        for profile in profiles:
            buyer_uri = self.parser.find_text(profile, "./cbc:BuyerProfileURI", namespaces=self.parser.nsmap)
            buyers.append(buyer_uri)

        for uri in buyers:
            organization = {
                "id": str(uuid.uuid4()),
                "roles": ["buyer"],
                "details": {
                    "buyerProfile": uri,
                }
            }
            self.parties.append(organization)
        return {}

    def fetch_bt60_lot_funding(self, root_element):
        funders = []
        lots = root_element.findall(".//cac:ProcurementProjectLot", namespaces=self.parser.nsmap)
        for lot in lots:
            lot_id = self.parser.find_text(lot, "./cbc:ID", namespaces=self.parser.nsmap)
            funding = lot.find(".//cbc:FundingProgramCode[@listName='eu-funded']", namespaces=self.parser.nsmap)
            if funding is not None and funding.text:
                funders.append({
                    "lot_id": lot_id,
                    "fundingProgramCode": funding.text,
                })

        # Update parties and their roles
        eu_funder = next((x for x in self.parties if x['name'] == "European Union"), None)
        if not eu_funder:
            eu_funder = {
                "id": str(uuid.uuid4()),  # Generate unique id.
                "name": "European Union",
                "roles": ["funder"]
            }
            self.parties.append(eu_funder)
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
            org_id = str(uuid.uuid4())  # Generate unique id.
            scheme, code, description = self.map_activity_code(activity["activityTypeCode"], 'Activity')
            self.parties.append({
                "id": org_id,
                "roles": ["buyer"],
                "details": {
                    "classifications": [
                        {
                            "scheme": scheme,
                            "id": code,
                            "description": description
                        }
                    ]
                }
            })
        return {}

    def fetch_bt740_contracting_entity(self, element):
        contracting_parties = element.findall(".//cac:ContractingPartyType", namespaces=self.parser.nsmap)
        for party in contracting_parties:
            party_type_code = self.parser.find_text(party, "./cbc:PartyTypeCode[@listName='buyer-contracting-type']", namespaces=self.parser.nsmap)
            if party_type_code:
                org = {
                    "id": str(uuid.uuid4()),
                    "roles": ["buyer"],
                    "details": {
                        "classifications": [
                            {
                                "scheme": "eu-buyer-contracting-type",
                                "id": party_type_code,
                                "description": self.get_contracting_entity_description(party_type_code),
                            }
                        ]
                    }
                }
                self.parties.append(org)
        return {}

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
    # various other fetch_opt_301_* methods have similar logic for mapping roles to organizations and linking to data structures.
                    
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
                    'country': self.convert_language_code(self.parser.find_text(org_element, './efac:Company/cac:PostalAddress/cac:Country/cbc:IdentificationCode', namespaces=self.parser.nsmap), code_type='country'),
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
                    'contactPoint': contact_point,
                    'details': {
                        'listedOnRegulatedMarket': self.fetch_listed_on_regulated_market(org_element),
                        'scale': self.fetch_company_size(org_element)
                    }
                }
                
                self.update_organization(organization, updated_info)
                logging.debug(f"Updated organization info: {organization}")

        for ubo_element in element.findall(".//efac:UltimateBeneficialOwner", namespaces=self.parser.nsmap):
            ubo_id = self.parser.find_text(ubo_element, "./cbc:ID", namespaces=self.parser.nsmap)
            if ubo_id:
                logging.debug(f"Processing UBO with ID: {ubo_id}")
                org_id = self.parser.find_text(ubo_element.getparent(), "./efac:Company/cac:PartyIdentification/cbc:ID", namespaces=self.parser.nsmap)
                organization = self.get_or_create_organization(organizations, org_id)
                
                first_name = self.parser.find_text(ubo_element, './cbc:FirstName', namespaces=self.parser.nsmap) or ""
                family_name = self.parser.find_text(ubo_element, './cbc:FamilyName', namespaces=self.parser.nsmap) or ""
                full_name = f"{first_name} {family_name}".strip() or "Unknown Beneficial Owner"
                
                ubo_info = {
                    "id": ubo_id,
                    "name": full_name,
                    "nationality": self.convert_language_code(self.parser.find_text(ubo_element, "./efac:Nationality/cbc:NationalityID", namespaces=self.parser.nsmap), code_type='country')
                }
                phone_info = self.fetch_bt503_ubo_contact(ubo_element)
                if phone_info:
                    ubo_info.update(phone_info)
                
                organization.setdefault("beneficialOwners", []).append(ubo_info)
                logging.debug(f"Updated organization with UBO: {organization}")

        return organizations
    
    def fetch_bt503_touchpoint_contact(self, org_element):
        telephone = self.parser.find_text(org_element, "./efac:TouchPoint/cac:Contact/cbc:Telephone", namespaces=self.parser.nsmap)
        return {"telephone": telephone} if telephone else {}

    def fetch_bt503_ubo_contact(self, ubo_element):
        telephone = self.parser.find_text(ubo_element, "./cac:Contact/cbc:Telephone", namespaces=self.parser.nsmap)
        return {"telephone": telephone} if telephone else {}

    def get_dispatch_date_time(self):
        # Fetch the root element of the XML.
        root = self.parser.root
        
        # Correctly target the cbc:IssueDate and cbc:IssueTime elements directly under the root or a specific parent.
        issue_date = self.parser.find_text(root, "./cbc:IssueDate", namespaces=self.parser.nsmap)
        issue_time = self.parser.find_text(root, "./cbc:IssueTime", namespaces=self.parser.nsmap)

        # Print extracted date and time for debugging purposes.
        print(f"Issue Date: {issue_date}")
        print(f"Issue Time: {issue_time}")

        # Check if both issue date and issue time are present.
        if issue_date and issue_time:
            # Combine the date and time strings into a single datetime string.
            combined_datetime = f"{issue_date[:10]}T{issue_time[:8]}{issue_date[10:]}"
            
            try:
                # Parse the combined date and time string into a datetime object.
                parsed_datetime = datetime.fromisoformat(combined_datetime)
                # Return the ISO formatted datetime string.
                return parsed_datetime.isoformat()
            except ValueError as e:
                # Log the error if the date and time could not be parsed.
                logging.error(f"Error parsing dispatch date/time: {combined_datetime} - {e}")
        else:
            # Log a warning if either the issue date or time is missing.
            logging.warning("Missing issue date or issue time in the XML.")

        # Return None if the date and time could not be parsed.
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

    def add_or_update_party(self, parties, party_info):
        for party in parties:
            if party['id'] == party_info['id']:
                for key, value in party_info.items():
                    if key == 'roles':
                        if 'roles' in party:
                            party['roles'] = list(set(party['roles'] + value))
                        else:
                            party['roles'] = value
                    elif key == 'contactPoint':
                        party.setdefault('contactPoint', {}).update(value)
                    elif key == 'details':
                        party.setdefault('details', {}).update(value)
                    else:
                        party[key] = value
                return
        parties.append(party_info)

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
        found = False
        for idx, doc in enumerate(self.tender.get("documents", [])):
            if doc["id"] == new_document["id"]:
                self.tender["documents"][idx] = new_document
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
                    'country': self.convert_language_code(self.parser.find_text(org_element, './efac:Company/cac:PostalAddress/cac:Country/cbc:IdentificationCode', namespaces=self.parser.nsmap), code_type='country'),
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

        for ubo_element in element.findall(".//efac:UltimateBeneficialOwner", namespaces=self.parser.nsmap):
            ubo_id = self.parser.find_text(ubo_element, "./cbc:ID", namespaces=self.parser.nsmap)
            if ubo_id:
                logging.debug(f"Processing UBO with ID: {ubo_id}")
                org_id = self.parser.find_text(ubo_element.getparent(), "./efac:Company/cac:PartyIdentification/cbc:ID", namespaces=self.parser.nsmap)
                organization = self.get_or_create_organization(organizations, org_id)
                
                first_name = self.parser.find_text(ubo_element, './cbc:FirstName', namespaces=self.parser.nsmap) or ""
                family_name = self.parser.find_text(ubo_element, './cbc:FamilyName', namespaces=self.parser.nsmap) or ""
                full_name = f"{first_name} {family_name}".strip() or "Unknown Beneficial Owner"

                # Fetch and process nationality to avoid NoneType error
                raw_nationality_code = self.parser.find_text(ubo_element, "./efac:Nationality/cbc:NationalityID", namespaces=self.parser.nsmap)
                processed_nationality_code = self.convert_language_code(raw_nationality_code, code_type='country') if raw_nationality_code else None
                
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

        return organizations
    
    def gather_party_info(self, root_element):
        logger = logging.getLogger(__name__)
        parties = []

        def add_or_update_party(existing_parties, new_party):
            existing_party = next((p for p in existing_parties if p['id'] == new_party['id']), None)
            if existing_party:
                for role in new_party.get('roles', []):
                    if role not in existing_party['roles']:
                        existing_party['roles'].append(role)
                for key, value in new_party.items():
                    if key == 'roles':
                        continue
                    elif isinstance(value, list):
                        existing_party.setdefault(key, []).extend(value)
                    elif isinstance(value, dict):
                        existing_party.setdefault(key, {}).update(value)
                    else:
                        existing_party[key] = value
            else:
                existing_parties.append(new_party)

        for org_element in root_element.findall(".//efac:Organizations/efac:Organization", namespaces=self.parser.nsmap):
            org_id = self.parser.find_text(org_element, "./efac:Company/cac:PartyIdentification/cbc:ID", namespaces=self.parser.nsmap)
            if org_id:
                org_info = {"id": org_id, "roles": [], "details": {}, "address": {}, "identifier": {}}
                name = self.parser.find_text(org_element, "./efac:Company/cac:PartyName/cbc:Name", namespaces=self.parser.nsmap)
                if name:
                    org_info["name"] = name
                
                contact_info = self.fetch_bt502_contact_point(org_element)
                if contact_info:
                    org_info["contactPoint"] = contact_info

                touchpoint_contact = self.fetch_bt503_touchpoint_contact(org_element)
                if touchpoint_contact:
                    org_info.setdefault('contactPoint', {}).update(touchpoint_contact)

                company_id = self.parser.find_text(org_element, "./efac:Company/cac:PartyLegalEntity/cbc:CompanyID", namespaces=self.parser.nsmap)
                if company_id:
                    org_info.setdefault("identifier", {})
                    org_info["identifier"]["id"] = company_id
                    org_info["identifier"]["scheme"] = "GB-COH"

                address = org_element.find('./efac:Company/cac:PostalAddress', namespaces=self.parser.nsmap)
                if address is not None:
                    org_info['address'] = {
                        "streetAddress": self.process_street_address(address, self.parser.nsmap),
                        "locality": self.parser.find_text(address, './cbc:CityName', namespaces=self.parser.nsmap),
                        "region": self.parser.find_text(address, './cbc:CountrySubentity', namespaces=self.parser.nsmap),
                        "postalCode": self.parser.find_text(address, './cbc:PostalZone', namespaces=self.parser.nsmap),
                        "country": self.convert_language_code(self.parser.find_text(address, './cac:Country/cbc:IdentificationCode', namespaces=self.parser.nsmap), code_type='country')
                    }

                add_or_update_party(parties, org_info)
            else:
                logger.warning('Party element found without an ID or Name!')

        for ubo_element in root_element.findall(".//efac:UltimateBeneficialOwner", namespaces=self.parser.nsmap):
            ubo_id = self.parser.find_text(ubo_element, "./cbc:ID", namespaces=self.parser.nsmap)
            if ubo_id:
                org_id = self.parser.find_text(ubo_element.getparent(), "./efac:Company/cac:PartyIdentification/cbc:ID", namespaces=self.parser.nsmap)
                organization = self.get_or_create_organization(parties, org_id)
                ubo_info = {"id": ubo_id}

                family_name = self.parser.find_text(ubo_element, "./cbc:FamilyName", namespaces=self.parser.nsmap)
                first_name = self.parser.find_text(ubo_element, "./cbc:FirstName", namespaces=self.parser.nsmap)
                ubo_info["name"] = f"{first_name} {family_name}".strip() if family_name or first_name else "Unknown Beneficial Owner"

                ubo_address = ubo_element.find('./cac:PostalAddress', namespaces=self.parser.nsmap)
                if ubo_address is not None:
                    ubo_info['address'] = self.process_ubo_address(ubo_address)

                phone_info = self.fetch_bt503_ubo_contact(ubo_element)
                if phone_info:
                    ubo_info.update(phone_info)

                organization.setdefault('beneficialOwners', []).append(ubo_info)
                add_or_update_party(parties, organization)

        return parties
    
    def process_ubo_address(self, address_element):
        country_element = self.parser.find_text(address_element, './cac:Country/cbc:IdentificationCode', namespaces=self.parser.nsmap)
        return {'country': self.convert_language_code(country_element, code_type='country')} if country_element else {}

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
        # Define a mapping of buyer legal type codes to descriptions based on the authority table
        legal_type_mapping = {
            "central-gov-agency": "Central government authority",
            "regional-gov-agency": "Regional or local authority",
            "body-pl": "Body governed by public law",
            "public-undertaking": "Public undertaking",
            # Add other codes and descriptions as needed
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
        tender_value_aggregate = {
            "amount": 0,
            "currency": None
        }
        part_lot_found = False  # Tracker for 'Part' flagged lots
        award_criteria_found = False  # Tracker for award criteria existence

        lot_elements = element.findall(".//cac:ProcurementProjectLot", namespaces=self.parser.nsmap)
        for lot_element in lot_elements:
            lot = self.parse_single_lot(lot_element)
            lots.append(lot)

            # Handle lot groups (if applicable)
            lot_group = self.parse_lot_group(lot_element)
            if lot_group:
                if 'lotGroups' not in lot:
                    lot['lotGroups'] = []
                lot['lotGroups'].append(lot_group)

            # Check if the lot was marked as a 'Part'
            if lot.get('isPartScheme'):
                part_lot_found = True
                if lot['value']['amount'] is not None:
                    if tender_value_aggregate['currency'] is None:
                        tender_value_aggregate['currency'] = lot['value']['currency']
                    if tender_value_aggregate['currency'] == lot['value']['currency']:
                        tender_value_aggregate['amount'] += lot['value']['amount']
                    else:
                        # Handle currency mismatch case if necessary; simplified example assumes same currency
                        print("Currency mismatch; additional logic required.")

            # Check if the lot has award criteria
            if 'awardCriteria' in lot and lot['awardCriteria']['criteria']:
                award_criteria_found = True

        # If there was a 'Part' lot and valid calculations, attach at tender level
        if part_lot_found and tender_value_aggregate['amount'] > 0:
            return lots, tender_value_aggregate, award_criteria_found

        return lots, None, award_criteria_found
    
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

        return lot

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
            "criteria": []
        }

        criteria_elements = lot_element.findall(".//cac:TenderingTerms/cac:AwardingTerms/cac:AwardingCriterion/cac:SubordinateAwardingCriterion", namespaces=self.parser.nsmap)

        for criterion in criteria_elements:
            criterion_details = {}

            # BT-539: Award Criterion Type
            criterion_type = self.parser.find_text(criterion, "./cbc:AwardingCriterionTypeCode[@listName='award-criterion-type']")
            if criterion_type:
                criterion_details['type'] = criterion_type

            # BT-540: Award Criterion Description
            criterion_description = self.parser.find_text(criterion, "./cbc:Description")
            if criterion_description:
                criterion_details['description'] = criterion_description

            # BT-541: Award Criterion Fixed Number, Threshold Number, Weight Number
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

            # BT-734: Award Criterion Name
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

    def fetch_notice_languages(self, element):
        languages = []
        notice_language_code = self.parser.find_text(element, ".//cbc:NoticeLanguageCode")
        if notice_language_code:
            language_iso = self.convert_language_code(notice_language_code, code_type='language')
            if language_iso:
                languages.append(language_iso.upper())

        logging.debug(f'Fetched notice languages: {languages}')
        return languages

    @staticmethod
    def convert_language_code(code, code_type='language'):
        """
        Convert codes based on the provided type: 'language' for language codes, 'country' for country codes.
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
            'ISL': 'is'   # Icelandic
        }

        country_mapping = {
            'GBR': 'GB',
            'USA': 'US',
            'DEU': 'DE',
            'FRA': 'FR',
            # Add other mappings as needed
        }

        if code_type == 'language':
            return language_mapping.get(code.upper())
        elif code_type == 'country':
            return country_mapping.get(code.upper())
        return None
   
    def parse_tender_values(self, root):
        tender_values = []
        tender_value_elements = root.findall(".//ext:UBLExtensions/ext:UBLExtension/ext:ExtensionContent/efext:EformsExtension/efac:NoticeResult/efac:LotTender", namespaces=self.parser.nsmap)
            
        for tender_value_element in tender_value_elements:
            tender_id = self.parser.find_text(tender_value_element, "./cbc:ID", namespaces=self.parser.nsmap)
            payable_amount = self.parser.find_text(tender_value_element, "./cac:LegalMonetaryTotal/cbc:PayableAmount", namespaces=self.parser.nsmap)
            currency_id = tender_value_element.find(".//cbc:PayableAmount", namespaces=self.parser.nsmap).get('currencyID')

            # Related information: Lot and Result ID linking
            lot_id = self.parser.find_text(tender_value_element, "./efac:TenderLot/cbc:ID", namespaces=self.parser.nsmap)
            result_id = self.parser.find_text(tender_value_element.getparent(), "./efac:LotResult/cbc:ID", namespaces=self.parser.nsmap)

            bids_detail = {
                "id": tender_id,
                "value": {
                    "amount": float(payable_amount) if payable_amount else None,
                    "currency": currency_id
                },
                "relatedLot": lot_id
            }
            
            tender_values.append(bids_detail)
            
            # Connect also the award
            award = {
                "id": result_id,
                "value": {
                    "amount": float(payable_amount) if payable_amount else None,
                    "currency": currency_id
                },
                "relatedLots": [lot_id]
            }
            
            self.add_update_award(award)

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

    def parse_classifications(self, project_element):
        classifications = []
        
        # Main classifications
        main_classifications = self.parser.find_nodes(project_element, "./cac:MainCommodityClassification")
        for classification in main_classifications:
            class_code = self.parser.find_text(classification, "./cbc:ItemClassificationCode")
            class_scheme = self.parser.find_attribute(classification, "./cbc:ItemClassificationCode", "listName")
            if class_code and class_scheme:
                classifications.append({
                    "id": class_code,
                    "scheme": class_scheme.upper(),  # as per requirement to capitalize the scheme name
                })

        # Additional classifications
        additional_classifications = self.parser.find_nodes(project_element, "./cac:AdditionalCommodityClassification")
        for classification in additional_classifications:
            class_code = self.parser.find_text(classification, "./cbc:ItemClassificationCode")
            if class_code:
                classifications.append({
                    "id": class_code,
                    "scheme": "CPV",  # Assuming CPV for additional classifications
                })

        return classifications
    
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

    def convert_tender_to_ocds(self):
        root = self.parser.root
        ocid = "ocds-" + str(uuid.uuid4())
        dispatch_datetime = self.get_dispatch_date_time()
        contract_signed_date = self.get_contract_signed_date()
        tender_title = self.parser.find_text(root, ".//cac:ProcurementProject/cbc:Name", namespaces=self.parser.nsmap)

        form_type = self.get_form_type(root)
        
        # Use the enhanced parsing method to include all necessary information
        self.parties = self.parse_organizations(root)
        self.fetch_bt506_emails(root)  # Fetch BT-506 emails
        self.fetch_bt505_urls(root)  # Fetch BT-505 URLs
        self.handle_bt14_and_bt707(root)  # Handle restricted documents logic

        activities = self.parse_activity_authority(root)
        for activity in activities:
            for party in self.parties:
                if "buyer" in party.get("roles", []):
                    party.setdefault("details", {}).setdefault("classifications", []).append(activity)

        legal_types = self.parse_buyer_legal_type(root)
        for legal_type in legal_types:
            for party in self.parties:
                if "buyer" in party.get("roles", []):
                    party.setdefault("details", {}).setdefault("classifications", []).append(legal_type)

        # Collecting and filling data for other required elements
        lots, aggregated_part_value, award_criteria_found = self.parse_lots(root)
        legal_basis = self.get_legal_basis(root)
        languages = self.fetch_notice_languages(root)
        additional_info = self.fetch_bt300_additional_info(root)
        tender_estimated_value = self.fetch_tender_estimated_value(root)

        document_language = languages[0] if languages else None

        procedure_type = self.parse_procedure_type(root)
        procurement_method_rationale, procurement_method_rationale_classifications = self.parse_direct_award_justification(root)
        procedure_features = self.parse_procedure_features(root)

        # Fetch bids details
        bids_details = self.parse_tender_values(root)

        # Construct tender object with fetched details
        tender = {
            "id": self.parser.find_text(root, ".//cbc:ContractFolderID"),
            "status": form_type['tender_status'],
            "title": tender_title,
            "description": additional_info,
            "legalBasis": legal_basis,
            "lang": languages,
            "lots": lots,
            "lotGroups": [] if aggregated_part_value else None,
            "awardCriteria": {
                "criteria": [criterion for lot in lots for criterion in lot.get('awardCriteria', {}).get('criteria', [])]
            } if award_criteria_found else None,
            "procurementMethod": procedure_type["method"] if procedure_type else None,
            "procurementMethodDetails": procedure_type["details"] if procedure_type else None,
            "procurementMethodRationale": procurement_method_rationale if procurement_method_rationale else None,
            "procurementMethodRationaleClassifications": procurement_method_rationale_classifications if procurement_method_rationale_classifications else None,
            "value": tender_estimated_value,
            "procedureFeatures": procedure_features if procedure_features else None,  # Add procedure features
        }

        # Process lots for URLs and electronic auctions
        for lot_element in self.parser.find_nodes(root, ".//cac:ProcurementProjectLot"):
            auction_url, submission_url = self.fetch_urls_for_lot(lot_element, 'Lot')
            lot_id = self.parser.find_text(lot_element, "./cbc:ID", namespaces=self.parser.nsmap)
            lot_info = {
                "id": lot_id,
                "techniques": {"electronicAuction": {"url": auction_url}} if auction_url else None,
                "submissionMethodDetails": submission_url if submission_url else None
            }

            # Process 'Part' URLs similarly
            part_auction_url, part_submission_url = self.fetch_urls_for_lot(lot_element, 'Part')
            if part_auction_url or part_submission_url:
                lot_info.update({
                    "techniques": {"electronicAuction": {"url": part_auction_url}} if part_auction_url else None,
                    "submissionMethodDetails": part_submission_url if part_submission_url else None
                })

            # Ensure only valid filled `lot_info` is appended
            if any(lot_info.values()):
                self.add_or_update_lot(tender['lots'], lot_info)

        # Filter out parties without valid IDs and sort parties to ensure the order of ORG-0004 before ORG-0001
        self.parties = [party for party in self.parties if party.get('id')]  # Remove parties without valid IDs
        self.parties = sorted(self.parties, key=lambda k: k['id'])

        release = {
            "id": self.parser.find_text(root, "./cbc:ID"),
            "ocid": ocid,
            "date": dispatch_datetime,
            "initiationType": "tender",
            "tag": form_type['tag'],
            "parties": self.parties,
            "language": document_language,
            "tender": tender,
            "relatedProcesses": self.parse_related_processes(root),
            "awards": self.awards,
            "contracts": [{
                "dateSigned": contract_signed_date
            }] if contract_signed_date else []
        }

        # Append bids details if they exist
        if bids_details:
            release['bids'] = {
                "details": bids_details
            }

        # Clean the release structure including removing 'scheme' from 'identifier'
        cleaned_release = self.clean_release_structure(release)
        cleaned_release = self.remove_schema_from_identifier(cleaned_release)  # Remove 'scheme' from 'identifier'
        
        logging.info('Conversion to OCDS format completed.')
        return cleaned_release


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
    
    def fetch_tender_estimated_value(self, root):
       value_element = root.find(".//cac:ProcurementProject/cac:RequestedTenderTotal/cbc:EstimatedOverallContractAmount", namespaces=self.parser.nsmap)
       if value_element is not None:
           amount = float(value_element.text) if value_element.text else None
           currency = value_element.get('currencyID')
           return {"amount": amount, "currency": currency}
       return None

def convert_ted_to_ocds(xml_file):
    logging.basicConfig(level=logging.DEBUG) 
    try:
        parser = XMLParser(xml_file)
        converter = TEDtoOCDSConverter(parser)
        release_info = converter.convert_tender_to_ocds()
        result = json.dumps({"releases": [release_info]}, indent=2, ensure_ascii=False)
        return result
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        raise

# Example usage
xml_file = "can_24_minimal.xml"
ocds_json = convert_ted_to_ocds(xml_file)
print(ocds_json)

