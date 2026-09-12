from copy import deepcopy

import pytest

from backend.domain.config import C
from backend.domain.models import TickPlan, TickSummary, create_initial_state
from agent_runner.contracts import BridgeContractError, ThoughtMapper, core_snapshot, current_tick_plan, game_rules, require_tick_plan
from agent_runner.core_port import CorePort
from agent_runner.fixtures import FixtureModel, FixtureSpecialist
from agent_runner.runner import SettlementTracker
from core_agent.core_agent import CoreAgent


@pytest.mark.parametrize("with_summary", [False, True])
def test_snapshot_preserves_authority_and_nonzero_pending(with_summary):
    state = create_initial_state()
    state.pending_food, state.pending_oxygen = 12.5, 31.7
    state.settings.generation = {next(iter(state.crew)): 0.25}
    state.settings.irrigation = [state.plots[2].id, state.plots[0].id]
    state.settings.water_production_l = 23.7
    state.last_summary = TickSummary(tick=state.tick) if with_summary else None
    raw = state.model_dump(mode="json")
    rules = game_rules()
    snapshot = core_snapshot(state, rules)
    assert snapshot["resources"] == {key: value["value"] for key, value in raw["resources"].items()}
    assert snapshot["resource_details"] == raw["resources"]
    for key in ("pending_food", "pending_oxygen", "settings", "last_summary", "paused", "paused_reason", "failed", "failure_reason", "speed", "tick", "version"):
        assert snapshot[key] == raw[key]
    assert snapshot["crew"] == list(raw["crew"].values())
    for source, plot in zip(raw["plots"], snapshot["plots"]):
        assert all(plot[key] == value for key, value in source.items())
    assert rules["irrigation"]["power_per_plot"] == C["irrigation"]["power_eu"]
    snapshot["settings"]["generation"].clear()
    assert state.settings.generation


@pytest.mark.parametrize("reason,failed,status", [("player", False, "paused"), ("error", False, "error_paused"), (None, True, "failed")])
def test_control_status_is_not_flattened(reason, failed, status):
    state = create_initial_state()
    state.paused, state.paused_reason, state.failed = bool(reason), reason, failed
    assert core_snapshot(state, game_rules())["world_status"] == status


@pytest.mark.asyncio
async def test_core_calls_both_specialists_and_result_is_next_context():
    class RecordingModel(FixtureModel):
        async def decide(self, context):
            self.context = context
            return await super().decide(context)
    model = RecordingModel()
    port = CorePort(CoreAgent(model, FixtureSpecialist(), FixtureSpecialist()), mock=True)
    state = create_initial_state()
    messages = []
    decision = await port.decide(state, [], messages.append)
    assert {message.agent for message in messages} == {"core", "plant", "human"}
    assert all(message.ts > 0 and message.payload["mock"] for message in messages)
    assert len({message.payload["conversation_id"] for message in messages}) == 1
    assert all("content" not in message.payload for message in messages)
    state.tick += 1
    state.version += 1
    state.last_summary = TickSummary(tick=state.tick)
    await port.accept_result(decision, state, [])
    await port.decide(state, [{"code": "EXAMPLE"}], messages.append)
    assert model.context["history"][0]["actual_summary"] == state.last_summary.model_dump()
    assert model.context["history"][-1]["errors"] == [{"code": "EXAMPLE"}]
    assert not any(message.kind == "reflection" for message in messages)


@pytest.mark.asyncio
async def test_entry_stage_offset_zero_only_and_core_order_preserved():
    snapshot = core_snapshot(create_initial_state(), game_rules())
    decision = await FixtureModel().decide({"world": snapshot})
    plan = decision["plan"]
    stage = plan["stages"][0]
    stage["max_ticks"] = 3
    crew = [c["id"] for c in snapshot["crew"]]
    def action(id, person, kind, offset=0, plot=None, crop=None, amount=1):
        return {"action_id": id, "crew_id": person, "kind": kind, "tick_offset": offset,
                "repeat": False, "plot_id": plot, "crop_type": crop, "amount": amount}
    stage["actions"] = [action("drink", crew[2], "drink", amount=0.2),
                         action("eat", crew[1], "eat", amount=12),
                         action("harvest", crew[0], "harvest", plot=snapshot["plots"][0]["id"]),
                         action("plant", crew[3], "plant", plot=snapshot["plots"][0]["id"], crop="lettuce"),
                         action("future", crew[1], "generate", offset=1)]
    translated = current_tick_plan(plan, snapshot)
    assert [refill.crew_id for refill in translated.refills] == [crew[2], crew[1]]
    assert [refill.amount for refill in translated.refills] == [0.2, 12]
    assert [operation.order for operation in translated.plot_ops] == [2, 3]
    assert translated.generation == {}
    del stage["water_liters_per_tick"]
    with pytest.raises(ValueError):
        current_tick_plan(plan, snapshot)


@pytest.mark.parametrize("field", ["refills", "generation", "water_production_l", "irrigation", "plot_ops", "state_version"])
def test_missing_settings_are_not_silently_filled(field):
    data = TickPlan(tick=0, state_version=0).model_dump()
    del data[field]
    with pytest.raises(BridgeContractError):
        require_tick_plan(data, 0, 0)


def test_settlement_requires_matching_plan_and_same_commit_summary():
    plan = TickPlan(tick=0, state_version=7)
    state = create_initial_state()
    state.version = 8
    state.tick = 1
    state.last_summary = TickSummary(tick=1)
    unrelated = SettlementTracker(plan)
    unrelated.accept("state_update", state.model_dump())
    assert unrelated.state is None and unrelated.stale
    tracker = SettlementTracker(plan)
    tracker.accept("tick_plan", plan.model_dump())
    tracker.accept("world_event", {"type": "plan_failed"})
    tracker.accept("state_update", state.model_dump())
    assert tracker.state == state
    assert tracker.events == [{"type": "plan_failed"}]
    interrupted = SettlementTracker(plan)
    interrupted.accept("tick_plan", plan.model_dump())
    state.version += 1
    interrupted.accept("state_update", state.model_dump())
    assert interrupted.state is None
