"""Wire boundary and initial-state tests; no strategy or settlement here."""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from pydantic import ValidationError

from backend.domain.config import C, CROPS
from backend.domain.models import Refill, TickPlan, WorldState, create_initial_state, tick_plan_schema


def test_guide_1_1_initial_public_stock_not_charged_for_crew() -> None:
    state = create_initial_state()
    assert set(state.resources) == set(C["resources"])
    for key, resource in state.resources.items():
        assert resource.value == C["resources"][key]["initial"]
        assert resource.capacity == C["resources"][key]["capacity"]
        assert resource.warning == C["resources"][key]["warning"]
    for crew in state.crew.values():
        assert crew.food_energy == C["crew"]["food_energy"]["initial"]
        assert crew.water == C["crew"]["water"]["initial"]


def test_guide_1_2_initial_population_and_crop_layout() -> None:
    state = create_initial_state()
    assert len(state.crew) == C["crew"]["count"]
    assert len(state.plots) == C["plots"]["count"]
    for crop in CROPS:
        assert sum(plot.crop == crop for plot in state.plots) == C["plots"]["initial_per_crop"]


def test_world_wire_roundtrip_and_snake_case() -> None:
    state = create_initial_state()
    wire = state.model_dump(mode="json")
    assert WorldState.model_validate_json(json.dumps(wire)) == state
    assert "pending_oxygen" in wire
    assert "food_energy" in next(iter(wire["crew"].values()))
    assert "water_production_l" in wire["settings"]
    assert "foodEnergy" not in json.dumps(wire)


def test_default_plan_is_empty_and_instances_do_not_share_settings() -> None:
    state = create_initial_state()
    other = create_initial_state()
    state.settings.irrigation.append(state.plots[0].id)
    assert other.settings.irrigation == []
    plan = TickPlan(tick=state.tick)
    assert plan.refills == plan.irrigation == plan.plot_ops == []
    assert plan.generation == {}
    assert plan.water_production_l == 0


def test_refill_preserves_requested_share_and_order() -> None:
    state = create_initial_state()
    crew_ids = list(state.crew)
    amount = C["crew"]["water"]["refill_max"] / 2
    plan = TickPlan(tick=state.tick, refills=[
        Refill(crew_id=crew_ids[-1], kind="water", amount=amount),
        Refill(crew_id=crew_ids[0], kind="water", amount=amount),
    ])
    assert [refill.crew_id for refill in plan.refills] == [crew_ids[-1], crew_ids[0]]
    assert plan.refills[0].amount == amount


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_plan_requests_rejected_at_wire_boundary(bad: float) -> None:
    with pytest.raises(ValidationError):
        TickPlan(tick=0, water_production_l=bad)
    with pytest.raises(ValidationError):
        TickPlan(tick=0, generation={"crew": bad})


def test_unknown_wire_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        TickPlan.model_validate({"tick": 0, "waterProductionL": 0})


def test_generated_plan_schema_accepts_wire_plan() -> None:
    state = create_initial_state()
    plan = TickPlan(tick=state.tick, state_version=state.version)
    jsonschema.Draft202012Validator.check_schema(tick_plan_schema())
    jsonschema.validate(plan.model_dump(mode="json"), tick_plan_schema())


def test_plan_schema_tracks_catalog_extension_without_logic_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(CROPS, "test_crop", dict(next(iter(CROPS.values()))))
    assert "test_crop" in tick_plan_schema()["$defs"]["PlotOp"]["properties"]["crop"]["anyOf"][0]["enum"]


def test_checked_in_schema_matches_generator() -> None:
    path = Path(__file__).resolve().parents[2] / "shared" / "tick_plan.schema.json"
    assert json.loads(path.read_text(encoding="utf-8")) == tick_plan_schema()
