"""Shared wire contracts. No world updates or specialist policies live here."""
from dataclasses import asdict, dataclass, field
from uuid import uuid4
from typing import Any
import math

class ContractError(ValueError):
    pass

@dataclass(frozen=True)
class Message:
    discussion_id: str
    round: int
    sender: str
    recipient: str
    world_version: int
    content: dict[str, Any]
    display_text: str = ""
    message_id: str = field(default_factory=lambda: str(uuid4()))
    explanation: dict[str, Any] | None = None

    def __post_init__(self):
        if not isinstance(self.display_text, str):
            raise ContractError('display_text must be plain text')
        if not isinstance(self.message_id, str) or not self.message_id:
            raise ContractError('message_id must be a nonempty string')
        if self.explanation is not None:
            validate_shape(self.explanation, EXPLANATION_SCHEMA)

    def to_dict(self):
        data = asdict(self)
        data['display_text'] = self.display_text or render_public_text(self.content)
        explanation = self.explanation or self.content.get('explanation')
        data['explanation'] = explanation
        data['detail_text'] = render_explanation(explanation) if explanation else ''
        return data


def render_public_text(content):
    """Legacy compatibility: render only public text, never stringify state/tool payloads."""
    for key in ('summary', 'question'):
        if isinstance(content.get(key), str) and content[key].strip():
            return content[key]
    lines = []
    for key, label in (('observations', '觀察'), ('priorities', '優先需求'),
                       ('acceptable_tradeoffs', '可接受的取捨'),
                       ('evidence_and_unknowns', '依據與不確定性')):
        value = content.get(key)
        if isinstance(value, str) and value.strip():
            lines.append(f'{label}：{value}')
        elif isinstance(value, list):
            texts = [v for v in value if isinstance(v, str) and v.strip()]
            if texts:
                lines.append(f'{label}：' + '；'.join(texts))
    return '\n'.join(lines) or '已收到結構化建議，尚未提供對話摘要。'



def obj(properties):
    return {'type': 'object', 'properties': properties,
            'required': list(properties), 'additionalProperties': False}


def array(items):
    return {'type': 'array', 'items': items}


STRING = {'type': 'string'}
NUMBER = {'type': 'number'}
INTEGER = {'type': 'integer'}
NULL_STRING = {'type': ['string', 'null']}
def bounded_number(maximum, description):
    return {'type': 'number', 'minimum': 0, 'maximum': maximum, 'description': description}


RESOURCES_SCHEMA = obj({
    'food': bounded_number(200000, '公共食物庫存，遊戲 kcal；Food是欄位名稱，不是另一種單位。'),
    'water': bounded_number(4000, '公共水庫存，L。'),
    'oxygen': bounded_number(15000, '公共氧氣庫存，OU。'),
    'power': bounded_number(10000, '公共電力庫存，EU。'),
})
CREW_SCHEMA = obj({'id': {'type': 'string', 'minLength': 1},
                   'food_energy': bounded_number(3000, '個人能量，遊戲 kcal；與公共food分開。'),
                   'water': bounded_number(2, '個人水存量，L；與公共water分開。')})
CREW_SCHEMA['properties']['alive'] = {'type': 'boolean', 'description': '必填，由世界後端提供實際存活狀態，不可推測或補預設值。'}
CREW_SCHEMA['required'].append('alive')
CREW_SCHEMA['additionalProperties'] = True
PLOT_SCHEMA = obj({'id': {'type': 'string', 'minLength': 1},
                   'crop_type': {'type': ['string', 'null'],
                                 'enum': ['lettuce', 'potato', 'tomato', 'wheat', 'soybean', None]},
                   'status': {'type': 'string', 'enum': ['empty', 'growing', 'mature', 'dead']},
                   'growth_ticks': {'type': 'integer', 'minimum': 0, 'maximum': 90},
                   'consecutive_unirrigated_ticks': {'type': 'integer', 'minimum': 0, 'maximum': 3}})
PLOT_SCHEMA['additionalProperties'] = True
WORLD_SCHEMA = obj({'world_version': {'type': 'integer', 'minimum': 0},
                    'world_status': {'type': 'string', 'enum': ['running', 'paused', 'planning', 'error_paused', 'failed']},
                    'snapshot_phase': {'type': 'string', 'enum': ['between_ticks']},
                    'rules_version': {'type': 'string', 'minLength': 1},
                    'tick': {'type': 'integer', 'minimum': 0},
                    'resources': RESOURCES_SCHEMA,
                    'crew': {'type': 'array', 'minItems': 4, 'maxItems': 4, 'items': CREW_SCHEMA},
                    'plots': {'type': 'array', 'minItems': 20, 'maxItems': 20, 'items': PLOT_SCHEMA}})
# Transport snapshots may include controller-owned status/current_plan/pause_token.
WORLD_SCHEMA['additionalProperties'] = True


def validate_world(world):
    validate_shape(world, WORLD_SCHEMA)
    if 'status' in world and world['status'] != world['world_status']:
        raise ContractError('legacy status conflicts with world_status')
    for collection in ('crew', 'plots'):
        ids = [item['id'] for item in world[collection]]
        if len(ids) != len(set(ids)):
            raise ContractError(f'duplicate {collection} ID')
    for plot in world['plots']:
        if (plot['status'] == 'empty') != (plot['crop_type'] is None):
            raise ContractError('empty plot must have null crop_type; occupied plot needs a crop')
        maturity = 30 if plot['crop_type'] == 'lettuce' else 90
        if plot['growth_ticks'] > maturity:
            raise ContractError('growth exceeds crop maturity')


ACTION = obj({
    'action_id': STRING, 'crew_id': STRING,
    'kind': {'type': 'string', 'enum': ['eat', 'drink', 'generate', 'plant', 'harvest', 'clear']},
    'tick_offset': INTEGER, 'repeat': {'type': 'boolean'},
    'plot_id': NULL_STRING, 'crop_type': NULL_STRING, 'amount': NUMBER,
})
CONDITION = obj({'path': STRING, 'op': {'type': 'string', 'enum': ['lt', 'lte', 'eq', 'gte', 'gt']}, 'value': NUMBER})
STAGE = obj({
    'stage_id': STRING, 'purpose': STRING, 'max_ticks': INTEGER,
    'water_liters_per_tick': NUMBER,
    'irrigation_order': array(STRING), 'actions': array(ACTION),
    'transitions': array(obj({'target_stage_id': STRING,
                              'match': {'type': 'string', 'enum': ['all', 'any']},
                              'conditions': array(CONDITION)})),
})
PLAN_SCHEMA = obj({'plan_id': STRING, 'rules_version': STRING,
                   'based_on_state_version': INTEGER, 'reason': STRING,
                   'entry_stage_id': STRING, 'stages': array(STAGE)})
EXPLANATION_SCHEMA = obj({
    'observations': array(STRING),
    'proposals': array(obj({'proposal_id': STRING, 'strategy': STRING, 'reason': STRING,
                          'expected_effect': STRING, 'tradeoffs': array(STRING),
                          'evidence': array(STRING)})),
    'reviews': array(obj({'message_id': STRING, 'proposal_id': STRING,
                         'disposition': {'type': 'string', 'enum': ['accept', 'modify', 'reject', 'needs_clarification']},
                         'assessment': STRING})),
    'conflicts': array(STRING), 'follow_up_reason': STRING, 'decision_reason': STRING,
    'uncertainties': array(STRING),
})


def empty_explanation():
    return {'observations': [], 'proposals': [], 'reviews': [], 'conflicts': [],
            'follow_up_reason': '', 'decision_reason': '', 'uncertainties': []}


def render_explanation(explanation):
    """Deterministic public narration, never invents reasoning from executable actions."""
    validate_shape(explanation, EXPLANATION_SCHEMA)
    parts = [f'觀察：{text}' for text in explanation['observations']]
    for proposal in explanation['proposals']:
        parts.extend([f'建議策略：{proposal["strategy"]}', f'原因：{proposal["reason"]}',
                      f'預期效果：{proposal["expected_effect"]}'])
        parts.extend(f'代價／讓步：{text}' for text in proposal['tradeoffs'])
        parts.extend(f'依據：{text}' for text in proposal['evidence'])
    labels = {'accept': '採納', 'modify': '調整', 'reject': '不採納', 'needs_clarification': '需要釐清'}
    for review in explanation['reviews']:
        parts.append(f'評估建議 {review["proposal_id"]}（{labels[review["disposition"]]}）：{review["assessment"]}')
    parts.extend(f'衝突：{text}' for text in explanation['conflicts'])
    if explanation['follow_up_reason']:
        parts.append('再次討論的原因：' + explanation['follow_up_reason'])
    if explanation['decision_reason']:
        parts.append('決策理由：' + explanation['decision_reason'])
    parts.extend(f'尚不確定：{text}' for text in explanation['uncertainties'])
    return '\n'.join(parts)


DECISION_SCHEMA = obj({
    'kind': {'type': 'string', 'enum': ['consult', 'final']},
    'summary': STRING, 'explanation': EXPLANATION_SCHEMA,
    'plant_question': STRING, 'human_question': STRING,
    'plan': {'anyOf': [PLAN_SCHEMA, {'type': 'null'}]},
})


def validate_shape(value, schema, path='$'):
    if 'anyOf' in schema:
        for branch in schema['anyOf']:
            try:
                validate_shape(value, branch, path)
                return
            except ContractError:
                pass
        raise ContractError(f'{path}: no matching schema')
    types = schema['type']
    types = types if isinstance(types, list) else [types]
    valid = {'null': value is None, 'string': isinstance(value, str),
             'boolean': type(value) is bool, 'integer': type(value) is int,
             'number': type(value) in (int, float) and math.isfinite(value),
             'array': isinstance(value, list), 'object': isinstance(value, dict)}
    if not any(valid[t] for t in types):
        raise ContractError(f'{path}: expected {types}')
    if 'enum' in schema and value not in schema['enum']:
        raise ContractError(f'{path}: invalid enum')
    if type(value) in (int, float):
        if value < schema.get('minimum', -math.inf) or value > schema.get('maximum', math.inf):
            raise ContractError(f'{path}: number outside range')
    if isinstance(value, str) and len(value) < schema.get('minLength', 0):
        raise ContractError(f'{path}: string too short')
    if isinstance(value, list) and not schema.get('minItems', 0) <= len(value) <= schema.get('maxItems', math.inf):
        raise ContractError(f'{path}: array length outside range')
    if isinstance(value, dict):
        if not set(schema.get('required', [])) <= set(value) or (schema.get('additionalProperties', True) is False and not set(value) <= set(schema['properties'])):
            raise ContractError(f'{path}: missing or unknown fields')
        for key, child in schema['properties'].items():
            if key in value:
                validate_shape(value[key], child, f'{path}.{key}')
    if isinstance(value, list):
        for i, child in enumerate(value):
            validate_shape(child, schema['items'], f'{path}[{i}]')


def validate_plan(plan, snapshot):
    validate_shape(plan, PLAN_SCHEMA)
    if plan['rules_version'] != snapshot['rules_version'] or plan['based_on_state_version'] != snapshot['world_version']:
        raise ContractError('plan uses stale state or different rules')
    stages = plan['stages']
    ids = [s['stage_id'] for s in stages]
    if not stages or len(set(ids)) != len(ids) or any(not i for i in ids) or plan['entry_stage_id'] not in ids:
        raise ContractError('invalid stage identifiers')
    crew = {c['id'] for c in snapshot['crew']}
    plots = {p['id'] for p in snapshot['plots']}
    paths = {'tick'} | {f'resources.{r}' for r in ('food', 'water', 'oxygen', 'power')}
    paths |= {f'crew.{c}.{r}' for c in crew for r in ('food_energy', 'water')}
    paths |= {f'plots.{p}.{r}' for p in plots for r in ('growth_ticks', 'consecutive_unirrigated_ticks')}
    action_ids = set()
    for stage in stages:
        if stage['max_ticks'] < 1 or not 0 <= stage['water_liters_per_tick'] <= 250:
            raise ContractError('invalid stage duration or water production')
        order = stage['irrigation_order']
        if len(set(order)) != len(order) or not set(order) <= plots:
            raise ContractError('invalid irrigation priority')
        assigned = {}
        for action in stage['actions']:
            aid, person, kind = action['action_id'], action['crew_id'], action['kind']
            if not aid or aid in action_ids or person not in crew:
                raise ContractError('duplicate action id or unknown crew')
            action_ids.add(aid)
            start = action['tick_offset']
            if not 0 <= start < stage['max_ticks']:
                raise ContractError('action outside stage')
            if action['repeat'] and kind not in ('generate',):
                raise ContractError('only generation can repeat; schedule other actions explicitly')
            occupied = range(start, stage['max_ticks']) if action['repeat'] else [start]
            # Pairwise intervals, without iterating arbitrarily large stage durations.
            interval = (occupied.start, occupied.stop-1) if isinstance(occupied, range) else (start, start)
            for lo, hi in assigned.get(person, []):
                if max(lo, interval[0]) <= min(hi, interval[1]):
                    raise ContractError('crew has overlapping work')
            assigned.setdefault(person, []).append(interval)
            limit = {'eat': 1000, 'drink': .5, 'generate': 1}.get(kind)
            if limit is not None:
                if not 0 < action['amount'] <= limit or action['plot_id'] is not None or action['crop_type'] is not None:
                    raise ContractError('invalid personal task parameters')
            else:
                if action['plot_id'] not in plots or action['amount'] != 1:
                    raise ContractError('invalid plot task')
                if kind == 'plant':
                    if action['crop_type'] not in ('lettuce', 'potato', 'tomato', 'wheat', 'soybean'):
                        raise ContractError('unknown crop')
                elif action['crop_type'] is not None:
                    raise ContractError('crop_type only applies to plant')
        for transition in stage['transitions']:
            if transition['target_stage_id'] not in ids or not transition['conditions']:
                raise ContractError('invalid transition')
            if any(c['path'] not in paths for c in transition['conditions']):
                raise ContractError('condition uses unsupported state path')
