"""Versioned game rules; exact decimal/rational arithmetic, never physiology overrides."""
import hashlib
import json
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES_PATH = ROOT / 'data/world_rules_v0.12.json'
RULES = json.loads(RULES_PATH.read_text(encoding='utf-8'))

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()

RULES_HASH = digest(RULES)

def F(value):
    return value if isinstance(value, Fraction) else Fraction(str(value))

ENERGY = F(RULES['crew']['daily_energy']) / 24
WATER = F(RULES['crew']['daily_water']) / 24
OXYGEN = F(RULES['crew']['daily_oxygen_kg']) * 1000 / 24

def json_numbers(value):
    if isinstance(value, Fraction):
        return float(value)
    if isinstance(value, dict):
        return {k: json_numbers(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_numbers(v) for v in value]
    return value

def get_world_rule(rule_ids):
    return [{'id': key, 'type': 'world_rule', 'title': key, 'document_id': 'world_rules_v0.12',
             'chunk_id': None, 'rule_id': key, 'locator': 'spec.md ' + RULES['rule_ids'][key]['section'],
             'source_url': None, 'excerpt': RULES['rule_ids'][key]['text'],
             'verification_status': 'world_defined'} for key in rule_ids if key in RULES['rule_ids']]
