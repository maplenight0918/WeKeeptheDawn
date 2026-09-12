"""Concurrency probes use planner gates, never elapsed wall time as synchronization."""
import asyncio

import pytest

from backend.domain.models import TickPlan, create_initial_state
from backend.domain.state import StateRepository
from backend.orchestration.event_bus import EventBus
from backend.orchestration.world_loop import WorldLoop


class GatedSource:
    def __init__(self):
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = []

    async def plan(self, state, events):
        self.calls.append(state.model_copy(deep=True))
        self.started.set()
        await self.release.wait()
        return TickPlan(tick=state.tick, state_version=state.version,
                        irrigation=[plot.id for plot in state.plots if plot.crop and not plot.dead])


def setup_loop():
    repository = StateRepository(create_initial_state())
    source = GatedSource()
    bus = EventBus()
    return WorldLoop(repository, bus, source), repository, source, bus


def resource_values(state):
    return {key: resource.value for key, resource in state.resources.items()}


async def start_planning(loop, source):
    task = asyncio.create_task(loop.tick())
    await asyncio.wait_for(source.started.wait(), timeout=3)
    return task


@pytest.mark.asyncio
async def test_pause_during_planning_prevents_settlement_until_resume():
    loop, repository, source, _ = setup_loop()
    initial = repository.get()
    task = await start_planning(loop, source)
    await loop.control('pause')
    source.release.set()
    await asyncio.wait_for(task, timeout=3)
    paused = repository.get()
    assert paused.paused
    assert paused.tick == initial.tick
    assert resource_values(paused) == resource_values(initial)
    assert all(plot.consecutive_unirrigated_ticks == 0 for plot in paused.plots)
    await loop.control('resume')
    await loop.tick()
    assert len(source.calls) == 2
    assert repository.get().tick == initial.tick + 1


@pytest.mark.asyncio
async def test_resource_edit_discards_inflight_plan_and_observes_new_version():
    loop, repository, source, _ = setup_loop()
    task = await start_planning(loop, source)
    await loop.edit_resources({'power': 300})
    source.release.set()
    await asyncio.wait_for(task, timeout=3)
    edited = repository.get()
    assert edited.tick == source.calls[0].tick
    assert edited.resources['power'].value == 300
    assert not edited.failed
    await loop.tick()
    assert len(source.calls) == 2
    assert source.calls[1].resources['power'].value == 300
    assert source.calls[1].version != source.calls[0].version
    assert repository.get().tick == edited.tick + 1


@pytest.mark.asyncio
async def test_reentrant_tick_cannot_create_another_plan_or_settlement():
    loop, repository, source, _ = setup_loop()
    before = repository.get()
    task = await start_planning(loop, source)
    await asyncio.wait_for(loop.tick(), timeout=3)
    assert len(source.calls) == 1
    assert repository.get().tick == before.tick
    source.release.set()
    await asyncio.wait_for(task, timeout=3)
    assert repository.get().tick == before.tick + 1
    assert len(source.calls) == 1


@pytest.mark.asyncio
async def test_player_death_envelope_precedes_snapshot_and_retains_deaths():
    loop, repository, _, bus = setup_loop()
    queue = bus.subscribe()
    await loop.edit_resources({'oxygen': 0})
    messages = []
    while not queue.empty():
        messages.append(queue.get_nowait())
    assert messages[0]['type'] == 'mission_failed'
    snapshots = [message['payload'] for message in messages if message['type'] == 'state_update']
    assert snapshots
    snapshot = snapshots[-1]
    if hasattr(snapshot, 'model_dump'):
        snapshot = snapshot.model_dump()
    assert snapshot['failed']
    assert all(not crew['alive'] for crew in snapshot['crew'].values())
    assert repository.get().failed


@pytest.mark.asyncio
async def test_reset_discards_inflight_plan_and_clears_continuous_settings():
    loop, repository, source, _ = setup_loop()
    initial = repository.get()
    initial.settings.generation = {next(iter(initial.crew)): 1}
    initial.settings.water_production_l = 100
    initial.settings.irrigation = [initial.plots[0].id]
    repository.set(initial)
    task = await start_planning(loop, source)
    await loop.reset()
    source.release.set()
    await asyncio.wait_for(task, timeout=3)
    reset = repository.get()
    expected = create_initial_state()
    assert reset.tick == expected.tick
    assert resource_values(reset) == resource_values(expected)
    assert reset.settings.model_dump() == expected.settings.model_dump()
    assert not reset.failed
    assert all(plot.consecutive_unirrigated_ticks == 0 for plot in reset.plots)
    await loop.tick()
    assert len(source.calls) == 2
    assert source.calls[1].settings.model_dump() == expected.settings.model_dump()
