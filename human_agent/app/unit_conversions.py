"""User-confirmed energy equivalence, separate from game accounting coefficients."""
import json
from app.world_rules import ROOT, F, digest

CONVERSIONS=json.loads((ROOT/'data/unit_conversions.json').read_text(encoding='utf-8'))
EU_TO_KWH=F(CONVERSIONS['eu_to_kwh'])

def eu_to_kwh(eu):
    value=F(eu)
    if value<0: raise ValueError('Energy must be nonnegative')
    return value*EU_TO_KWH

def energy_to_eu(value,unit='kWh'):
    value=F(value)
    if value<0 or unit not in {'Wh','kWh'}: raise ValueError('Expected nonnegative Wh or kWh energy')
    return value/(1000 if unit=='Wh' else 1)/EU_TO_KWH

def conversion_evidence():
    return {'id':'unit_conversion.eu_kwh','type':'implementation_assumption',
        'title':'User-confirmed EU energy conversion','document_id':'unit_conversions',
        'chunk_id':None,'rule_id':None,'locator':'data/unit_conversions.json', 'source_url':None,
        'excerpt':'User confirmed 1 EU = 3.9745 kWh = 3974.5 Wh. EU = kWh / 3.9745. kW is power, not energy; duration is required. Game conversion coefficients remain unchanged.',
        'verification_status':'user_confirmed','reviewed_claims':[]}

def conversion_context():
    return {'eu_to_kwh':float(EU_TO_KWH),'version':CONVERSIONS['version'],'hash':digest(CONVERSIONS),
            'source':'User confirmed; supersedes older Core text stating no EU mapping.',
            'scope':CONVERSIONS['scope']}
