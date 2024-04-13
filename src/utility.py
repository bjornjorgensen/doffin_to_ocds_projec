from lxml import etree

def extract_legal_basis(xml_path):
    tree = etree.parse(xml_path)
    ns = {
        'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
        'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
    }
    
    xpath_expression = "/*/cac:TenderingTerms/cac:ProcurementLegislationDocumentReference[cbc:ID[not(.='CrossBorderLaw' or .='LocalLegalBasis')]]"
    
    legal_basis_elements = tree.xpath(xpath_expression, namespaces=ns)
    
    for element in legal_basis_elements:
        legal_basis_id = element.find('cbc:ID', namespaces=ns).text
        scheme_name = element.find('cbc:ID', namespaces=ns).get('schemeName')
        description_element = element.find('cbc:DocumentDescription', namespaces=ns)

        description = description_element.text if description_element is not None else None

        if scheme_name == 'ELI':
            return {
                "scheme": scheme_name,
                "id": legal_basis_id,
                "description": description  # Now includes description
            }
    return None