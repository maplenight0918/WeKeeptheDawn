"""One authoritative, deterministic inventory transition. No repository or I/O."""
from __future__ import annotations

import math

from backend.domain.config import C
from backend.domain.models import TickSummary, ContinuousSettings
from backend.engine.crew import check_deaths, consume_baseline, refill
from backend.engine.crops import update_crops
from backend.engine.events import emit
from backend.engine.generation import generate
from backend.engine.harvest import execute_plot_ops
from backend.engine.water_plant import produce_water


class WorldEngine:
    @staticmethod
    def _settle(state, plan):
        state = state.model_copy(deep=True)
        events, errors = [], []
        summary = TickSummary(tick=state.tick)
        if state.paused or state.paused_reason is not None or state.failed:
            return state, summary, events, errors
        # The agreed pending variant reserves capacity when produced and commits
        # here; it never enters WorldLoop/StateRepository as a separate mutation.
        for key in ("oxygen", "food"):
            pending = getattr(state, f"pending_{key}")
            state.resources[key].value = min(state.resources[key].capacity, state.resources[key].value + pending)
            setattr(state, f"pending_{key}", 0)
        state.tick += 1
        state.version += 1
        summary.tick = state.tick
        for crew in state.crew.values():
            crew.work_this_tick = 0
            if crew.alive:
                crew.current_task = "idle"
        if not check_deaths(state, summary, events):
            refill(state, plan, summary)
            consume_baseline(state, summary, events)
        if not state.failed:
            generate(state, plan, summary, events)
        if not state.failed:
            produce_water(state, plan, summary, events)
        if not state.failed:
            update_crops(state, plan, summary, events)
            execute_plot_ops(state, plan, summary, events, errors)
        if not state.failed:
            for key, resource in state.resources.items():
                if resource.value < resource.warning:
                    emit(state, events, "resource_low", key, value=resource.value, warning=resource.warning)
            for crew in state.crew.values():
                for field in ("food_energy", "water"):
                    if crew.alive and getattr(crew, field) < C["crew"][field]["warning"]:
                        emit(state, events, "crew_low_supply", crew.id, field=field, value=getattr(crew, field))
        state.settings = ContinuousSettings(generation=dict(plan.generation),
                                            water_production_l=plan.water_production_l,
                                            irrigation=list(plan.irrigation))
        state.last_summary = summary
        return state, summary, events, errors

    @classmethod
    def settle(cls, state, plan):
        next_state, summary, events, _ = cls._settle(state, plan)
        return next_state, summary, events

    @classmethod
    def validate_plan_execution(cls, state, plan):
        """Internal single-tick validation projection, never an Agent tool."""
        return cls._settle(state, plan)[3]

    @staticmethod
    def edit_resources(state, values):
        state = state.model_copy(deep=True)
        events = []
        for key, value in values.items():
            if key not in state.resources or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"Invalid resource edit: {key}")
        state.version += 1
        for key, value in values.items():
            state.resources[key].value = min(state.resources[key].capacity, max(0, value))
            if key in ("oxygen", "food"):
                setattr(state, f"pending_{key}", 0)
        summary = TickSummary(tick=state.tick)
        check_deaths(state, summary, events)
        emit(state, events, "player_edit", values=dict(values))
        return state, events
