import asyncio
from copy import deepcopy
import unittest
from unittest.mock import patch
from core_agent import CoreAgent, Message, PlanningError, validate_plan, ContractError
from core_agent.rules import get_rules
from core_agent.contracts import empty_explanation, render_explanation, validate_world
from core_agent.adapters import GPTDecisionModel
from examples.offline_demo import FixtureModel, FixtureSpecialist, sample_snapshot, sample_decision


class CoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_world_resources_are_required_before_calling_agents(self):
        for key in ('food', 'water', 'oxygen', 'power'):
            world = sample_snapshot(); del world['resources'][key]
            with self.assertRaises(PlanningError):
                await CoreAgent(FixtureModel(), FixtureSpecialist(), FixtureSpecialist()).plan(world, get_rules())

    async def test_specialists_require_actual_snapshot_facts(self):
        for field in ('world_status', 'snapshot_phase'):
            world = sample_snapshot()
            del world[field]
            with self.assertRaises(PlanningError):
                await CoreAgent(FixtureModel(), FixtureSpecialist(), FixtureSpecialist()).plan(world, get_rules())
        world = sample_snapshot()
        del world['crew'][0]['alive']
        with self.assertRaises(ContractError): validate_world(world)
        world = sample_snapshot(); world['snapshot_phase'] = 'mid_tick'
        with self.assertRaises(ContractError): validate_world(world)

    async def test_failed_facts_never_rewritten_for_specialists(self):
        for mutation in ('failed', 'dead'):
            world = sample_snapshot()
            if mutation == 'failed': world['world_status'] = 'failed'
            else: world['crew'][0]['alive'] = False
            with self.assertRaises(PlanningError):
                await CoreAgent(FixtureModel(), FixtureSpecialist(), FixtureSpecialist()).plan(world, get_rules())

    async def test_running_facts_and_resource_values_pass_through(self):
        world = sample_snapshot()
        result = await CoreAgent(FixtureModel(), FixtureSpecialist(), FixtureSpecialist()).plan(world, get_rules())
        for message in result.transcript[:2]:
            self.assertEqual(message.content['world'], world)
            self.assertEqual(message.content['world']['world_status'], 'running')

    def test_plant_hourly_electricity_matches_reference(self):
        rules = get_rules()
        per_tick = rules['irrigation']['power_per_plot']
        self.assertEqual(rules['rules_version'], 'greenhouse-2026-09-12-v2')
        # Full 100 m² daily demand must match the unrounded equipment model.
        self.assertAlmostEqual(per_tick * 20 * 24 * 3.9745, 397.4608695652174)
        self.assertAlmostEqual(per_tick, 0.208339030887)
        self.assertEqual(rules['generation']['power'], 250)
        self.assertEqual(rules['irrigation']['water_per_plot'], 8.7)

    def test_world_units_ranges_and_unique_ids(self):
        for wrong in ('3000', -1, 4001, float('nan')):
            world = sample_snapshot(); world['resources']['water'] = wrong
            with self.assertRaises(ContractError): validate_world(world)
        world = sample_snapshot(); world['crew'][1]['id'] = world['crew'][0]['id']
        with self.assertRaises(ContractError): validate_world(world)
        world = sample_snapshot(); world['crew'][0]['alive'] = True
        world['status'] = 'running'; validate_world(world)

    async def test_final_and_no_world_mutation(self):
        state = sample_snapshot(); before = deepcopy(state); events = []
        result = await CoreAgent(FixtureModel(), FixtureSpecialist(), FixtureSpecialist()).plan(
            state, get_rules(), on_event=events.append)
        self.assertEqual(state, before)
        self.assertEqual(len(result.transcript), 5)
        self.assertEqual(len(events), 5)
        validate_plan(result.plan, state)

    def test_dialogue_text_and_stable_id(self):
        message = Message('d', 1, 'plant', 'core', 0, {'observations': ['缺水風險'],
                          'world': {'private_payload': 'not for display'}})
        first, second = message.to_dict(), message.to_dict()
        self.assertEqual(first['message_id'], second['message_id'])
        self.assertEqual(first['display_text'], '觀察：缺水風險')
        explicit = Message('d', 1, 'human', 'core', 0, {}, display_text='我建議先補充飲水。')
        self.assertEqual(explicit.to_dict()['display_text'], '我建議先補充飲水。')
        with self.assertRaises(ContractError):
            Message('d', 1, 'human', 'core', 0, {}, display_text={})

    async def test_multiround_peer_messages(self):
        seen = []
        class Expert(FixtureSpecialist):
            async def ask(self, message):
                seen.append(message)
                return await super().ask(message)
        class Model(FixtureModel):
            async def decide(self, ctx):
                if ctx['round'] == 1:
                    explanation = empty_explanation()
                    explanation['follow_up_reason'] = '需要釐清灌溉與crew補充安排的衝突。'
                    return dict(explanation=explanation, kind='consult', summary='Need tradeoffs', plant_question='Reduce area?',
                                human_question='Available work?', plan=None)
                return await super().decide(ctx)
        result = await CoreAgent(Model(), Expert(), Expert()).plan(sample_snapshot(), get_rules())
        self.assertEqual(len(result.transcript), 10)
        self.assertTrue(any(m['sender'] == 'human' for m in seen[2].content['previous_messages']))
        self.assertIn('需要釐清', seen[2].to_dict()['detail_text'])

    async def test_unknown_review_rejected(self):
        class Model(FixtureModel):
            async def decide(self, context):
                result = await super().decide(context)
                result['explanation']['reviews'] = [dict(message_id='invented', proposal_id='invented',
                    disposition='accept', assessment='不是實際存在的建議')]
                return result
        with self.assertRaises(PlanningError):
            await CoreAgent(Model(), FixtureSpecialist(), FixtureSpecialist()).plan(sample_snapshot(), get_rules())

    def test_rich_explanation_is_rendered(self):
        explanation = empty_explanation()
        explanation['proposals'] = [dict(proposal_id='p1', strategy='保留作物', reason='避免失去收成',
            expected_effect='延續生長', tradeoffs=['持續耗電'], evidence=['遊戲規則'])]
        explanation['conflicts'] = ['電力也需要用於製水']
        explanation['follow_up_reason'] = '需要Human確認工作安排'
        text = render_explanation(explanation)
        for phrase in ('保留作物', '避免失去收成', '持續耗電', '電力也需要用於製水', '需要Human確認工作安排'):
            self.assertIn(phrase, text)

    async def test_round_limit(self):
        class Model:
            async def decide(self, context):
                explanation = empty_explanation()
                explanation['follow_up_reason'] = '仍需釐清。'
                return dict(explanation=explanation, kind='consult', summary='', plant_question='', human_question='', plan=None)
        with self.assertRaises(PlanningError):
            await CoreAgent(Model(), FixtureSpecialist(), FixtureSpecialist()).plan(sample_snapshot(), get_rules())

    async def test_wrong_reply_version(self):
        class Expert(FixtureSpecialist):
            async def ask(self, req):
                reply = await super().ask(req)
                return Message(reply.discussion_id, reply.round, reply.sender, 'core', 99, reply.content)
        with self.assertRaises(PlanningError):
            await CoreAgent(FixtureModel(), Expert(), FixtureSpecialist()).plan(sample_snapshot(), get_rules())

    async def test_timeout(self):
        class Expert:
            async def ask(self, req): await asyncio.sleep(1)
        with self.assertRaises(PlanningError):
            await CoreAgent(FixtureModel(), Expert(), Expert(), timeout=.01).plan(sample_snapshot(), get_rules())

    def test_stale_plan_and_conflicting_work(self):
        state = sample_snapshot(); plan = sample_decision(state)['plan']
        plan['based_on_state_version'] = 9
        with self.assertRaises(ContractError): validate_plan(plan, state)
        plan['based_on_state_version'] = 0
        conflict = deepcopy(plan['stages'][0]['actions'][0]); conflict['action_id'] = 'eat'
        conflict['kind'] = 'eat'; conflict['amount'] = 500
        plan['stages'][0]['actions'].append(conflict)
        with self.assertRaises(ContractError): validate_plan(plan, state)

    def test_stage_branches_and_bad_path(self):
        state = sample_snapshot(); plan = sample_decision(state)['plan']
        second = deepcopy(plan['stages'][0]); second['stage_id'] = 'next'; second['actions'] = []
        plan['stages'].append(second)
        plan['stages'][0]['transitions'] = [dict(target_stage_id='next', match='all',
            conditions=[dict(path='resources.oxygen', op='gte', value=9000)])]
        validate_plan(plan, state)
        plan['stages'][0]['transitions'][0]['conditions'][0]['path'] = '__import__("os")'
        with self.assertRaises(ContractError): validate_plan(plan, state)

    def test_nonfinite_and_unknown_ids(self):
        for value in (float('nan'), float('inf'), -1, 251):
            state = sample_snapshot(); plan = sample_decision(state)['plan']
            plan['stages'][0]['water_liters_per_tick'] = value
            with self.assertRaises(ContractError): validate_plan(plan, state)

    async def test_gpt_adapter_payload_and_refusal(self):
        import json
        decision = sample_decision(sample_snapshot())
        response = {'status': 'completed', 'output': [{'type': 'message', 'content': [
            {'type': 'output_text', 'text': json.dumps(decision)}]}]}
        with patch('core_agent.adapters.post_json', return_value=response) as post:
            model = GPTDecisionModel(model='test-model', api_key='test-key')
            self.assertEqual(await model.decide({'world': sample_snapshot()}), decision)
            payload = post.call_args.args[1]
            self.assertTrue(payload['text']['format']['strict'])
            self.assertFalse(payload['store'])
        with patch('core_agent.adapters.post_json', return_value={'status': 'incomplete'}):
            with self.assertRaises(PlanningError): await model.decide({})


if __name__ == '__main__': unittest.main()
