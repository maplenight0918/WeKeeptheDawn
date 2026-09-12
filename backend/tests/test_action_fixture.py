import pytest

from agent_runner.contracts import core_snapshot, current_tick_plan, game_rules
from agent_runner.core_port import CorePort
from agent_runner.fixtures import ActionFixtureModel, FixtureSpecialist
from backend.domain.models import create_initial_state
from backend.engine.world_engine import WorldEngine
from backend.orchestration.plan_validator import PlanValidator
from core_agent.core_agent import CoreAgent


@pytest.mark.asyncio
async def test_full_action_fixture_from_real_initial_state():
    state = create_initial_state()
    port = CorePort(CoreAgent(ActionFixtureModel(), FixtureSpecialist(), FixtureSpecialist()), mock=True)
    seen = set()
    harvest_ticks = []
    cleared = []
    for _ in range(40):
        before = state.model_dump()
        messages = []
        decision = await port.decide(state, [], messages.append)
        assert state.model_dump() == before  # No manufactured maturity or supplies.
        assert all(m.payload["mock"] for m in messages)
        assert not PlanValidator.check(state, decision.plan)
        state, summary, events = WorldEngine.settle(state, decision.plan)
        assert not state.failed
        assert not summary.irrigation.failed
        assert summary.water_plant.actual > 0
        seen.update(c.current_task for c in state.crew.values())
        if summary.harvested:
            harvest_ticks.append(state.tick)
            assert state.pending_food > 0
        cleared.extend(summary.cleared)
        for planting in summary.planted:
            assert next(p for p in state.plots if p.id == planting.plot_id).progress_ticks == 0
        await port.accept_result(decision, state, [e.model_dump() for e in events])
    assert {"generating", "eating", "drinking", "clearing", "planting", "harvesting"} <= seen
    assert cleared == [create_initial_state().plots[-1].id]
    assert harvest_ticks and min(harvest_ticks) > game_rules()["crops"]["lettuce"]["maturity_ticks"]


@pytest.mark.asyncio
async def test_action_fixture_is_repeatable_and_uses_supplied_rules():
    state = create_initial_state()
    state.tick = 7
    state.version = 19
    rules = game_rules()
    rules["irrigation"]["water_per_plot"] = 3
    rules["crew"]["refill_limit"]["drink"] = 0.25
    snapshot = core_snapshot(state, rules)
    context = {"world": snapshot, "rules": rules}
    model = ActionFixtureModel()
    first = await model.decide(context)
    assert first == await model.decide(context)
    plan = current_tick_plan(first["plan"], snapshot)
    assert plan.water_production_l == len(state.plots) * 3 + 0.25
    assert not plan.plot_ops  # No replay of the tick-zero clear.
    assert all(not action["repeat"] and action["tick_offset"] == 0
               for action in first["plan"]["stages"][0]["actions"])
