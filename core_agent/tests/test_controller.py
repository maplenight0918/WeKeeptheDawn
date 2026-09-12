import asyncio
from copy import deepcopy
import unittest
from core_agent import CoreController, CoreAgent, PlanningError
from core_agent.rules import get_rules
from examples.offline_demo import sample_snapshot, sample_decision, FixtureSpecialist


class World:
    def __init__(self):
        self.state = sample_snapshot()
        self.state.update(world_status='running', current_plan=sample_decision(self.state)['plan'])
        self.pauses = 0; self.applied = []; self.conflict = False
    async def observe(self): return deepcopy(self.state)
    async def pause_for_core(self, version):
        if self.conflict or self.state['world_version'] != version or self.state['world_status'] not in ('running',):
            return None
        self.pauses += 1
        self.state.update(world_status='planning', pause_token='owned')
        return deepcopy(self.state)
    async def apply_and_resume(self, plan, expected_version, pause_token):
        if self.state['world_version'] != expected_version or self.state['world_status'] != 'planning': return False
        self.applied.append(plan); self.state.update(world_status='running', current_plan=plan)
        return True


class Model:
    def __init__(self, decision='continue'):
        self.decision = decision; self.assessments = 0
    async def assess(self, context):
        self.assessments += 1
        return dict(decision=self.decision, reason='upcoming harvest')
    async def decide(self, context): return sample_decision(context['world'])


class ControllerTests(unittest.IsolatedAsyncioTestCase):
    def setup_controller(self, model=None):
        world = World(); model = model or Model()
        core = CoreAgent(model, FixtureSpecialist(), FixtureSpecialist())
        return CoreController(core, world, get_rules()), world, model

    async def test_assesses_while_running_without_pause(self):
        c,w,m = self.setup_controller()
        await c.step(); await asyncio.sleep(.01); await c.step()
        self.assertEqual(m.assessments, 1); self.assertEqual(w.pauses, 0)
        await c.step(); self.assertEqual(m.assessments, 1)
        await c._cancel_assessment()

    async def test_gpt_proactive_replan_uses_fresh_snapshot(self):
        c,w,m = self.setup_controller(Model('replan'))
        await c.step(); await asyncio.sleep(.01)
        w.state['tick'] = 1; w.state['world_version'] = 1
        await c.step()
        self.assertEqual(w.pauses, 1)
        self.assertEqual(w.applied[0]['based_on_state_version'], 1)
        self.assertEqual(w.state['world_status'], 'running')

    async def test_immediate_risk_preempts_slow_gpt(self):
        class Slow(Model):
            async def assess(self, context): await asyncio.sleep(10)
        c,w,m = self.setup_controller(Slow())
        await c.step()
        w.state['resources']['water'] = 300
        w.state['world_version'] += 1
        await c.step()
        self.assertEqual(w.pauses, 1); self.assertIsNone(c._assessment)

    async def test_manual_pause_not_resumed(self):
        c,w,m = self.setup_controller()
        w.state['world_status'] = 'paused'
        await c.step()
        self.assertEqual(w.pauses, 0); self.assertEqual(m.assessments, 0)

    async def test_compare_and_swap_conflict(self):
        c,w,m = self.setup_controller()
        w.state['current_plan'] = None; w.conflict = True
        await c.step()
        self.assertFalse(w.applied)

    async def test_failed_planning_keeps_pause(self):
        class Bad(Model):
            async def decide(self, context): raise PlanningError('offline')
        c,w,m = self.setup_controller(Bad())
        w.state['current_plan'] = None
        with self.assertRaises(PlanningError): await c.step()
        self.assertEqual(w.state['world_status'], 'planning'); self.assertFalse(w.applied)

    async def test_player_change_during_planning_not_overwritten(self):
        c,w,m = self.setup_controller()
        async def changed(context):
            w.state['world_version'] += 1; w.state['world_status'] = 'paused'
            return sample_decision(context['world'])
        m.decide = changed; w.state['current_plan'] = None
        await c.step()
        self.assertEqual(w.state['world_status'], 'paused'); self.assertFalse(w.applied)

    async def test_failed_world_stops_loop(self):
        c,w,m = self.setup_controller()
        w.state['world_status'] = 'failed'
        self.assertFalse(await c.step())

    async def test_cancel_stops_assessment(self):
        class Slow(Model):
            async def assess(self, context): await asyncio.sleep(10)
        c,w,m = self.setup_controller(Slow())
        stop = asyncio.Event()
        task = asyncio.create_task(c.run(stop))
        await asyncio.sleep(.01); stop.set(); await task
        self.assertIsNone(c._assessment)
