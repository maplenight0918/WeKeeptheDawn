"""Independent numerical invariants; randomized inputs are tests, never a policy."""
from __future__ import annotations

import random

import pytest

from backend.domain.config import C, crew_consumption_per_tick
from backend.domain.models import TickPlan, create_initial_state
from backend.engine.world_engine import WorldEngine


def test_guide_2_4_generation_shortage_preserves_requested_proportions():
    state = create_initial_state()
    state.plots = []
    crew_ids = list(state.crew)
    requests = {crew_ids[0]: 1, crew_ids[1]: 0.5}
    state.resources['power'].value = state.resources['power'].capacity - C['generation']['power_per_work'] / 2
    result, summary, _ = WorldEngine.settle(state, TickPlan(tick=state.tick, generation=requests))
    baseline = crew_consumption_per_tick()['food_energy']
    used = [state.crew[key].food_energy - baseline - result.crew[key].food_energy for key in requests]
    assert used[0] == pytest.approx(used[1] * 2)
    assert summary.generation.actual == pytest.approx(0.5)
    assert result.resources['power'].value == pytest.approx(state.resources['power'].capacity)


def test_guide_1_1_random_valid_requests_never_exceed_resource_bounds():
    rng = random.Random(917)
    for _ in range(80):
        state = create_initial_state()
        for resource in state.resources.values():
            resource.value = rng.uniform(0.01, resource.capacity)
        plan = TickPlan(
            tick=state.tick,
            generation={key: rng.random() * C['generation']['max_work_per_crew'] for key in state.crew},
            water_production_l=rng.random() * C['water_plant']['max_l_per_tick'] * 2,
            irrigation=rng.sample([plot.id for plot in state.plots], len(state.plots)),
        )
        result, _, _ = WorldEngine.settle(state, plan)
        for key, resource in result.resources.items():
            pending = getattr(result, 'pending_' + key, 0)
            assert resource.value >= 0
            assert resource.value + pending <= resource.capacity + 1e-8
        for crew in result.crew.values():
            assert crew.food_energy >= 0
            assert crew.water >= 0


def test_guide_2_6_settlement_is_deterministic():
    state = create_initial_state()
    plan = TickPlan(tick=state.tick)
    assert WorldEngine.settle(state, plan) == WorldEngine.settle(state, plan)
