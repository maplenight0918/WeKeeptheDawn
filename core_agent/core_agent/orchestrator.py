import asyncio
from dataclasses import dataclass
from copy import deepcopy
from typing import Protocol
from uuid import uuid4
from .contracts import Message, ContractError, DECISION_SCHEMA, validate_shape, validate_plan, empty_explanation, EXPLANATION_SCHEMA, validate_world


class Specialist(Protocol):
    async def ask(self, message: Message) -> Message: ...


class DecisionModel(Protocol):
    async def decide(self, context: dict) -> dict: ...


class PlanningError(RuntimeError):
    """Caller must keep the world paused; no fallback plan is executed."""


@dataclass
class PlanningResult:
    discussion_id: str
    plan: dict
    transcript: list[Message]

    def to_dict(self):
        return {'discussion_id': self.discussion_id, 'plan': self.plan,
                'transcript': [m.to_dict() for m in self.transcript]}


class CoreAgent:
    def __init__(self, model: DecisionModel, plant: Specialist, human: Specialist,
                 *, max_rounds=3, timeout=60):
        if not 1 <= max_rounds <= 3 or timeout <= 0:
            raise ValueError('max_rounds must be 1..3 and timeout positive')
        self.model, self.specialists = model, {'plant': plant, 'human': human}
        self.max_rounds, self.timeout = max_rounds, timeout

    async def plan(self, snapshot: dict, rules: dict, *, reason='initial', history=None,
                   current_plan=None, on_event=None) -> PlanningResult:
        state = deepcopy(snapshot)
        try:
            validate_world(state)
        except ContractError as exc:
            raise PlanningError('invalid world snapshot') from exc
        if type(state['world_version']) is not int or state['rules_version'] != rules.get('rules_version'):
            raise PlanningError('snapshot/rules version mismatch')
        if state['world_status'] == 'failed' or any(not c['alive'] for c in state['crew']):
            raise PlanningError('cannot plan for a failed world or dead crew')
        discussion_id = str(uuid4())
        transcript = []

        def emit(message):
            transcript.append(message)
            if on_event:
                on_event(message.to_dict())

        follow_up_reason = reason
        questions = {'plant': '請僅以電、水、固定二氧化碳條件評估植物策略、成長與產出，並提供繁體中文摘要。',
                     'human': '請以水、氧氣、電、食物評估crew存活與工作安排，並提供繁體中文摘要。'}
        try:
            for round_no in range(1, self.max_rounds + 1):
                # Both experts see the complete previous round, never a partial peer response.
                previous = [m.to_dict() for m in transcript]
                requests = []
                for name in self.specialists:
                    request_explanation = empty_explanation()
                    request_explanation['follow_up_reason'] = follow_up_reason
                    request = Message(discussion_id, round_no, 'core', name, state['world_version'],
                                      {'question': questions[name], 'world': state, 'rules': deepcopy(rules),
                                       'analysis_scope': (['power', 'water', 'carbon_dioxide'] if name == 'plant'
                                                          else ['water', 'oxygen', 'power', 'food']),
                                       'unit_conversion_policy': 'Core傳送世界原始數值與單位，不轉換文獻單位。專家自行完成文獻與世界單位、時間基準的換算；回覆可執行建議須使用世界單位，並在evidence_and_unknowns說明換算依據或缺少的映射。電力依rules.electricity_reference採1 EU=3.9745 kWh，按世界小時換算，不套用植物生長加速。電力及跨角色資源分配由Core決定。',
                                       'previous_messages': previous, 'reason': reason,
                                       'response_guidance': '請在外層 display_text 提供2至4句繁體中文對話：觀察、建議、取捨或不確定性。這是公開理由摘要，不是內部思考鏈；不得聲稱操作已執行。另須提供explanation結構：觀察、各項建議策略／理由／效果／代價／依據、回覆其他建議的評估與不確定性。',
                                       'explanation_schema': EXPLANATION_SCHEMA},
                                      explanation=request_explanation)
                    emit(request)
                    requests.append(request)
                results = await asyncio.gather(*[
                    asyncio.wait_for(self.specialists[r.recipient].ask(deepcopy(r)), self.timeout)
                    for r in requests], return_exceptions=True)
                for request, reply in zip(requests, results):
                    if isinstance(reply, BaseException):
                        raise PlanningError(f'{request.recipient} unavailable') from reply
                    if not isinstance(reply, Message) or (reply.discussion_id, reply.round, reply.sender,
                        reply.recipient, reply.world_version) != (discussion_id, round_no, request.recipient,
                                                                 'core', state['world_version']):
                        raise PlanningError('specialist reply has stale or incorrect routing')
                    required = {'observations', 'priorities', 'suggested_actions',
                                'acceptable_tradeoffs', 'evidence_and_unknowns'}
                    if not isinstance(reply.content, dict) or not required <= reply.content.keys():
                        raise PlanningError('specialist recommendation fields missing')
                    if reply.explanation is None:
                        raise PlanningError('specialist must supply structured public explanation')
                    validate_shape(reply.explanation, EXPLANATION_SCHEMA)
                    proposals = reply.explanation['proposals']
                    ids = [p['proposal_id'] for p in proposals]
                    if any(not i for i in ids) or len(ids) != len(set(ids)):
                        raise PlanningError('specialist proposal IDs must be unique and nonempty')
                    if any(m.message_id == reply.message_id for m in transcript):
                        raise PlanningError('duplicate message_id')
                    emit(reply)
                context = {'world': state, 'rules': rules, 'reason': reason,
                           'round': round_no, 'must_finalize': round_no == self.max_rounds,
                           'messages': [m.to_dict() for m in transcript],
                           'history': history or [], 'current_plan': current_plan}
                decision = await asyncio.wait_for(self.model.decide(deepcopy(context)), self.timeout)
                validate_shape(decision, DECISION_SCHEMA)
                references = {(m.message_id, p['proposal_id']) for m in transcript
                              if m.explanation for p in m.explanation['proposals']}
                for review in decision['explanation']['reviews']:
                    if (review['message_id'], review['proposal_id']) not in references:
                        raise ContractError('review references unknown proposal')
                if decision['kind'] == 'final':
                    if not decision['explanation']['decision_reason'].strip():
                        raise ContractError('final decision requires a public decision reason')
                    if decision['plan'] is None:
                        raise ContractError('final decision requires a plan')
                    validate_plan(decision['plan'], state)
                    emit(Message(discussion_id, round_no, 'core', 'all', state['world_version'], decision))
                    return PlanningResult(discussion_id, decision['plan'], transcript)
                if not decision['explanation']['follow_up_reason'].strip():
                    raise ContractError('consult requires a public follow-up reason')
                follow_up_reason = decision['explanation']['follow_up_reason']
                if decision['plan'] is not None:
                    raise ContractError('consult decision must not include executable plan')
                emit(Message(discussion_id, round_no, 'core', 'all', state['world_version'], decision))
                questions = {'plant': decision['plant_question'], 'human': decision['human_question']}
            raise PlanningError('discussion limit reached without valid final plan')
        except (ContractError, asyncio.TimeoutError, OSError) as exc:
            raise PlanningError('planning failed; keep world paused') from exc
