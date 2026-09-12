from __future__ import annotations

import pytest

from backend.domain.config import C, CROPS
from backend.domain.models import PlotOp, Refill, TickPlan, create_initial_state
from backend.orchestration.plan_validator import PlanValidator


@pytest.mark.parametrize("expected", [
    "CREW_DEAD", "CREW_DOUBLE_BOOKED", "GENERATION_OUT_OF_RANGE", "GENERATION_STATION_FULL",
    "WATER_REQUEST_NEGATIVE", "PLOT_NOT_EMPTY", "PLOT_NOT_MATURE", "PLOT_DEAD_NEEDS_CLEAR",
    "PLOT_UNKNOWN", "CROP_UNKNOWN", "SAME_CREW_HARVEST_AND_PLANT", "IRRIGATION_PLOT_INVALID",
    "CREW_UNKNOWN", "PLAN_STALE", "WORLD_FAILED", "REFILL_REQUEST_NEGATIVE", "IRRIGATION_DUPLICATE",
    "PLOT_ORDER_INVALID", "PLOT_ORDER_DUPLICATE",
])
def test_each_validator_error_code(expected: str) -> None:
    state = create_initial_state()
    ids = list(state.crew)
    crew_id = ids[0]
    plot = state.plots[0]
    crop = plot.crop
    plan = TickPlan(tick=state.tick, state_version=state.version)
    work = C["generation"]["max_work_per_crew"]
    refill = C["crew"]["food_energy"]["refill_max"]

    def op(kind: str, actor: str = crew_id, order: int = 0) -> PlotOp:
        return PlotOp(order=order, crew_id=actor, plot_id=plot.id, op=kind, crop=crop if kind == "plant" else None)

    if expected == "CREW_DEAD":
        state.crew[crew_id].alive = False
        plan.generation[crew_id] = work
    elif expected == "CREW_DOUBLE_BOOKED":
        plan.refills = [Refill(crew_id=crew_id, kind="food", amount=refill)]
        plan.generation[crew_id] = work / 2
    elif expected == "GENERATION_OUT_OF_RANGE":
        plan.generation[crew_id] = work * 2
    elif expected == "GENERATION_STATION_FULL":
        extra = state.crew[crew_id].model_copy(update={"id": "extra"})
        state.crew[extra.id] = extra
        plan.generation = {key: work for key in state.crew}
    elif expected == "WATER_REQUEST_NEGATIVE":
        plan.water_production_l = -C["water_plant"]["max_l_per_tick"]
    elif expected == "PLOT_NOT_EMPTY":
        plan.plot_ops = [op("plant")]
    elif expected == "PLOT_NOT_MATURE":
        plan.plot_ops = [op("harvest")]
    elif expected == "PLOT_DEAD_NEEDS_CLEAR":
        plot.dead = True
        plan.plot_ops = [op("plant")]
    elif expected == "PLOT_UNKNOWN":
        plan.irrigation = ["missing"]
    elif expected == "CROP_UNKNOWN":
        plan.plot_ops = [op("plant").model_copy(update={"crop": "missing"})]
    elif expected == "SAME_CREW_HARVEST_AND_PLANT":
        plan.plot_ops = [op("harvest"), op("plant", order=1)]
    elif expected == "IRRIGATION_PLOT_INVALID":
        plot.crop = None
        plan.irrigation = [plot.id]
    elif expected == "CREW_UNKNOWN":
        plan.generation["missing"] = work
    elif expected == "PLAN_STALE":
        plan.state_version = state.version + 1
    elif expected == "WORLD_FAILED":
        state.failed = True
    elif expected == "REFILL_REQUEST_NEGATIVE":
        plan.refills = [Refill(crew_id=crew_id, kind="food", amount=-refill)]
    elif expected == "IRRIGATION_DUPLICATE":
        plan.irrigation = [plot.id, plot.id]
    elif expected == "PLOT_ORDER_INVALID":
        plan.plot_ops = [op("clear", order=-1)]
    elif expected == "PLOT_ORDER_DUPLICATE":
        plan.plot_ops = [op("clear"), op("plant", actor=ids[1])]
    errors = PlanValidator.check(state, plan)
    assert expected in {error.code for error in errors}, errors


@pytest.mark.parametrize("field", ["water_production_l", "generation"])
def test_non_finite_wire_requests_have_explicit_error(field: str) -> None:
    state = create_initial_state()
    payload = {"tick": state.tick, field: float("nan") if field == "water_production_l" else {next(iter(state.crew)): float("inf")}}
    assert "NON_FINITE_NUMBER" in {error.code for error in PlanValidator.check(state, payload)}


def test_invalid_schema_has_explicit_error() -> None:
    assert "PLAN_SCHEMA_INVALID" in {error.code for error in PlanValidator.check(create_initial_state(), {"tick": "bad"})}


def test_valid_but_lethal_work_is_not_rejected_as_strategy() -> None:
    from backend.domain.config import crew_consumption_per_tick

    state = create_initial_state()
    crew_id = next(iter(state.crew))
    work = C["generation"]["max_work_per_crew"]
    state.crew[crew_id].food_energy = crew_consumption_per_tick()["food_energy"] + C["generation"]["food_energy_per_work"] * work
    plan = TickPlan(tick=state.tick, generation={crew_id: work})
    assert PlanValidator.check(state, plan) == []


def test_validation_sees_growth_phase_maturity_without_mutating_state() -> None:
    state = create_initial_state()
    plot = state.plots[0]
    plot.progress_ticks = CROPS[plot.crop]["maturity_ticks"] - 1
    before = state.model_dump()
    plan = TickPlan(tick=state.tick, irrigation=[plot.id], plot_ops=[
        PlotOp(order=0, crew_id=next(iter(state.crew)), plot_id=plot.id, op="harvest")
    ])
    assert PlanValidator.check(state, plan) == []
    assert state.model_dump() == before


def test_ordered_harvest_then_plant_uses_different_crew() -> None:
    state = create_initial_state()
    plot = state.plots[0]
    plot.mature = True
    plot.progress_ticks = CROPS[plot.crop]["maturity_ticks"]
    ids = list(state.crew)
    plan = TickPlan(tick=state.tick, plot_ops=[
        PlotOp(order=1, crew_id=ids[1], plot_id=plot.id, op="plant", crop=plot.crop),
        PlotOp(order=0, crew_id=ids[0], plot_id=plot.id, op="harvest"),
    ])
    assert PlanValidator.check(state, plan) == []
