"""Validate feasibility and occupancy without choosing or repairing Core policy."""
from __future__ import annotations

import math
from collections import Counter
from typing import Any

from pydantic import ValidationError as SchemaError

from backend.domain.config import C, CROPS
from backend.domain.models import TickPlan, ValidationError, WorldState


class PlanValidator:
    @staticmethod
    def check(state: WorldState, plan: TickPlan | dict[str, Any]) -> list[ValidationError]:
        errors: list[ValidationError] = []

        def report(code: str, target: str | None, message: str) -> None:
            errors.append(ValidationError(code=code, target=target, message=message))

        if not isinstance(plan, TickPlan):
            try:
                plan = TickPlan.model_validate(plan)
            except SchemaError as exc:
                for error in exc.errors():
                    code = "NON_FINITE_NUMBER" if error["type"] == "finite_number" else "PLAN_SCHEMA_INVALID"
                    report(code, ".".join(map(str, error["loc"])), error["msg"])
                return errors

        if plan.tick != state.tick or (plan.state_version is not None and plan.state_version != state.version):
            report("PLAN_STALE", "tick", "Plan tick or observed state version is stale")
        if state.failed:
            report("WORLD_FAILED", None, "The mission has already failed")

        plots = {plot.id: plot for plot in state.plots}
        assignments: dict[str, list[str]] = {}

        def assign(crew_id: str, task: str) -> None:
            if crew_id not in state.crew:
                report("CREW_UNKNOWN", crew_id, "Crew id does not exist")
            elif not state.crew[crew_id].alive:
                report("CREW_DEAD", crew_id, "A dead crew member cannot work")
            assignments.setdefault(crew_id, []).append(task)

        active_generators = 0
        for crew_id, requested in plan.generation.items():
            if crew_id not in state.crew:
                report("CREW_UNKNOWN", crew_id, "Crew id does not exist")
            if not math.isfinite(requested):
                report("NON_FINITE_NUMBER", crew_id, "Work request must be finite")
            elif not 0 <= requested <= C["generation"]["max_work_per_crew"]:
                report("GENERATION_OUT_OF_RANGE", crew_id, "Work request is outside the configured range")
            elif requested > 0:
                active_generators += 1
                assign(crew_id, "generation")
        if active_generators > C["generation"]["stations"]:
            report("GENERATION_STATION_FULL", "generation", "Requested workers exceed station capacity")

        for refill in plan.refills:
            assign(refill.crew_id, refill.kind)
            if not math.isfinite(refill.amount):
                report("NON_FINITE_NUMBER", refill.crew_id, "Refill amount must be finite")
            elif refill.amount < 0:
                report("REFILL_REQUEST_NEGATIVE", refill.crew_id, "Refill amount cannot be negative")
        if not math.isfinite(plan.water_production_l):
            report("NON_FINITE_NUMBER", "water_production_l", "Water request must be finite")
        elif plan.water_production_l < 0:
            report("WATER_REQUEST_NEGATIVE", "water_production_l", "Water request cannot be negative")

        for plot_id, count in Counter(plan.irrigation).items():
            if plot_id not in plots:
                report("PLOT_UNKNOWN", plot_id, "Plot id does not exist")
            elif plots[plot_id].crop is None or plots[plot_id].dead:
                report("IRRIGATION_PLOT_INVALID", plot_id, "Only living planted plots can be irrigated")
            if count > 1:
                report("IRRIGATION_DUPLICATE", plot_id, "A plot can receive only one irrigation allocation per tick")

        for op in plan.plot_ops:
            assign(op.crew_id, op.op)
            if op.plot_id not in plots:
                report("PLOT_UNKNOWN", op.plot_id, "Plot id does not exist")
            if op.crop is not None and op.crop not in CROPS:
                report("CROP_UNKNOWN", op.crop, "Crop key is not in the shared catalog")
            if op.op == "plant" and op.crop is None:
                report("CROP_UNKNOWN", op.plot_id, "Planting requires a crop key")
            if op.order < 0:
                report("PLOT_ORDER_INVALID", op.plot_id, "Operation order cannot be negative")
        for order, count in Counter(op.order for op in plan.plot_ops).items():
            if count > 1:
                report("PLOT_ORDER_DUPLICATE", str(order), "Operation order must be unambiguous")
        for crew_id, tasks in assignments.items():
            if len(tasks) > 1:
                report("CREW_DOUBLE_BOOKED", crew_id, "Crew has multiple occupied tasks in this tick")
            if "harvest" in tasks and "plant" in tasks:
                report("SAME_CREW_HARVEST_AND_PLANT", crew_id, "Harvesting and planting require distinct crew")

        if errors:
            return errors

        # Reuse engine rules at their actual phase boundaries, never a second set
        # of conversion formulas or a future-trajectory tool exposed to agents.
        from backend.engine.world_engine import WorldEngine

        return WorldEngine.validate_plan_execution(state, plan)
