"""Independent boundary checks; fixture choices are not engine policies."""
import pytest

from backend.domain.config import C, CROPS, harvest_food
from backend.domain.models import PlotOp, TickPlan, create_initial_state
from backend.engine.world_engine import WorldEngine
from backend.orchestration.player import edit_resources


def plan_for(state, **kwargs):
    return TickPlan(tick=state.tick, state_version=state.version, **kwargs)


def mature(plot, crop="potato"):
    plot.crop = crop
    plot.progress_ticks = CROPS[crop]["maturity_ticks"]
    plot.mature = True


def test_guide_2_2_pending_reserves_capacity_between_two_harvests():
    state = create_initial_state()
    one_yield = harvest_food("potato")
    state.resources["food"].value = state.resources["food"].capacity - one_yield
    a, b = state.plots[:2]
    mature(a)
    mature(b)
    crew_ids = list(state.crew)
    plan = plan_for(state, plot_ops=[
        PlotOp(order=0, crew_id=crew_ids[0], plot_id=a.id, op="harvest"),
        PlotOp(order=1, crew_id=crew_ids[1], plot_id=b.id, op="harvest"),
    ])
    result, summary, events = WorldEngine.settle(state, plan)
    assert [h.plot_id for h in summary.harvested] == [a.id]
    assert result.pending_food == pytest.approx(one_yield)
    assert result.resources["food"].value + result.pending_food == pytest.approx(
        result.resources["food"].capacity)
    assert result.plots[0].crop is None
    assert result.plots[1].mature
    assert any(e.type == "harvest_blocked_capacity" and e.target == b.id for e in events)


def test_guide_2_6_harvest_crop_maturing_this_tick():
    state = create_initial_state()
    plot = state.plots[0]
    plot.progress_ticks = CROPS[plot.crop]["maturity_ticks"] - 1
    crew_id = next(iter(state.crew))
    result, summary, _ = WorldEngine.settle(state, plan_for(
        state, irrigation=[plot.id], plot_ops=[
            PlotOp(order=0, crew_id=crew_id, plot_id=plot.id, op="harvest")]))
    assert len(summary.harvested) == 1
    assert result.plots[0].crop is None
    assert result.pending_food == pytest.approx(harvest_food(plot.crop))


def test_guide_3_2_distinct_crew_harvest_then_plant_in_core_order():
    state = create_initial_state()
    plot = state.plots[0]
    mature(plot)
    a, b = list(state.crew)[:2]
    # Deliberately reverse array order: explicit order remains authoritative.
    plan = plan_for(state, plot_ops=[
        PlotOp(order=1, crew_id=b, plot_id=plot.id, op="plant", crop="wheat"),
        PlotOp(order=0, crew_id=a, plot_id=plot.id, op="harvest"),
    ])
    result, summary, _ = WorldEngine.settle(state, plan)
    assert len(summary.harvested) == len(summary.planted) == 1
    assert result.plots[0].crop == "wheat"
    assert result.plots[0].progress_ticks == 0
    assert result.plots[0].consecutive_unirrigated_ticks == 0
    assert not result.plots[0].mature


@pytest.mark.parametrize("missing", ["water", "power"])
def test_guide_2_1_partial_irrigation_never_deducts_other_resource(missing):
    state = create_initial_state()
    state.resources[missing].value = C["irrigation"][
        "water_l" if missing == "water" else "power_eu"] / 2
    before = {key: state.resources[key].value for key in ("water", "power")}
    plot = state.plots[0]
    result, summary, _ = WorldEngine.settle(state, plan_for(state, irrigation=[plot.id]))
    assert {key: result.resources[key].value for key in before} == before
    assert summary.irrigation.water_used == summary.irrigation.power_used == 0
    assert result.plots[0].consecutive_unirrigated_ticks == C["irrigation"]["warning_after_ticks"]
    assert result.plots[0].progress_ticks == plot.progress_ticks
    assert result.pending_oxygen == 0


def test_guide_2_6_settle_does_not_mutate_state_or_plan():
    state = create_initial_state()
    state.pending_food = harvest_food("lettuce")
    state.pending_oxygen = CROPS["lettuce"]["oxygen_per_tick"]
    plan = plan_for(state, irrigation=[state.plots[0].id])
    before_state, before_plan = state.model_dump(), plan.model_dump()
    result, _, _ = WorldEngine.settle(state, plan)
    assert state.model_dump() == before_state
    assert plan.model_dump() == before_plan
    assert result is not state
    result.crew[next(iter(result.crew))].name = "changed result only"
    assert state.model_dump() == before_state


def test_guide_1_4_failed_world_does_not_merge_pending_or_resume():
    state = create_initial_state()
    state.failed = True
    state.failure_reason = "oxygen"
    state.resources["oxygen"].value = 0
    state.pending_oxygen = C["resources"]["oxygen"]["initial"]
    for crew in state.crew.values():
        crew.alive = False
        crew.death_reason = "oxygen"
        crew.current_task = "dead"
    before = state.model_dump()
    result, _, _ = WorldEngine.settle(state, plan_for(state))
    assert result.model_dump() == before
    assert state.model_dump() == before


@pytest.mark.parametrize("edited", ["food", "oxygen"])
def test_guide_2_6_player_edit_clears_only_matching_pending(edited):
    state = create_initial_state()
    state.pending_food = harvest_food("lettuce")
    state.pending_oxygen = CROPS["lettuce"]["oxygen_per_tick"]
    before = state.model_dump()
    other = "oxygen" if edited == "food" else "food"
    value = C["resources"][edited]["warning"]
    result, events = edit_resources(state, {edited: value})
    assert getattr(result, f"pending_{edited}") == 0
    assert getattr(result, f"pending_{other}") == getattr(state, f"pending_{other}")
    assert result.resources[edited].value == value
    assert result.tick == state.tick
    assert result.version > state.version
    assert state.model_dump() == before
    assert any(event.type == "player_edit" for event in events)


def test_guide_1_4_player_oxygen_resupply_does_not_revive_failed_crew():
    state = create_initial_state()
    failed, death_events = edit_resources(state, {"oxygen": 0})
    assert failed.failed
    assert all(not crew.alive for crew in failed.crew.values())
    assert any(event.type == "mission_failed" for event in death_events)
    supplied, _ = edit_resources(failed, {"oxygen": C["resources"]["oxygen"]["capacity"]})
    assert supplied.failed
    assert all(not crew.alive for crew in supplied.crew.values())
    result, _, _ = WorldEngine.settle(supplied, plan_for(supplied))
    assert result.model_dump() == supplied.model_dump()
