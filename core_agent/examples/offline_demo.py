"""Offline communication demo. Scripted responses are NOT real agents or GPT."""
import asyncio
import json
from core_agent import CoreAgent, Message
from core_agent.rules import get_rules
from core_agent.contracts import empty_explanation


def sample_snapshot():
    return {'world_version': 0, 'rules_version': get_rules()['rules_version'], 'tick': 0,
            'world_status': 'running', 'snapshot_phase': 'between_ticks',
            'resources': {'water': 3000, 'food': 120000, 'oxygen': 8000, 'power': 6000},
            'crew': [{'id': f'crew-{i}', 'food_energy': 2400, 'water': 1.5, 'alive': True} for i in range(4)],
            'plots': [{'id': f'plot-{i}', 'crop_type': crop, 'status': 'growing',
                       'growth_ticks': 0, 'consecutive_unirrigated_ticks': 0}
                      for i, crop in enumerate([c for c in get_rules()['crops'] for _ in range(4)])]}


def sample_decision(world):
    explanation = empty_explanation()
    explanation['decision_reason'] = '離線示範：先提交一個tick的工作安排，再評估最新狀態。'
    return {'kind': 'final', 'summary': 'Offline fixture: one-hour plan, then reassess.',
            'plant_question': '', 'human_question': '', 'explanation': explanation,
            'plan': {'plan_id': 'offline-example', 'rules_version': world['rules_version'],
                     'based_on_state_version': world['world_version'],
                     'reason': 'Fixture for testing the wire contract, not GPT reasoning.',
                     'entry_stage_id': 'initial', 'stages': [
                         {'stage_id': 'initial', 'purpose': 'Example only', 'max_ticks': 1,
                          'water_liters_per_tick': 174.5361666667,
                          'irrigation_order': [p['id'] for p in world['plots']],
                          'actions': [{'action_id': f'work-{c["id"]}', 'crew_id': c['id'],
                                       'kind': 'generate', 'tick_offset': 0, 'repeat': False,
                                       'plot_id': None, 'crop_type': None, 'amount': 1}
                                      for c in world['crew']], 'transitions': []}]}}


class FixtureSpecialist:
    async def ask(self, request):
        explanation = empty_explanation()
        explanation['observations'] = ['離線示範資料，不代表真實專家評估。']
        explanation['proposals'] = [{'proposal_id': f'{request.recipient}-proposal-{request.round}',
            'strategy': '先維持基準供應，並安排下一次檢查。',
            'reason': '此例僅示範建議如何透過API傳遞。',
            'expected_effect': '提供可呈現的結構化建議，不保證策略安全。',
            'tradeoffs': ['仍需Core整合另一方需求。'], 'evidence': ['離線測試fixture']}]
        return Message(request.discussion_id, request.round, request.recipient, 'core',
                       request.world_version, {'observations': ['Offline fixture'],
                       'priorities': ['crew survival'], 'suggested_actions': [],
                       'acceptable_tradeoffs': [], 'evidence_and_unknowns': ['No real expert called']},
                       explanation=explanation)


class FixtureModel:
    async def decide(self, context):
        return sample_decision(context['world'])


async def main():
    core = CoreAgent(FixtureModel(), FixtureSpecialist(), FixtureSpecialist())
    result = await core.plan(sample_snapshot(), get_rules())
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
