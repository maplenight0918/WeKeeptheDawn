from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from backend.domain.models import TickPlan, create_initial_state
from backend.domain.state import StateRepository
from backend.integration.sources import ExternalPlanSource
from backend.orchestration.event_bus import EventBus
from backend.orchestration.world_loop import WorldLoop


def test_external_submit_makes_an_isolated_wire_copy() -> None:
    async def scenario():
        state = create_initial_state()
        source = ExternalPlanSource(EventBus())
        plan = TickPlan(tick=state.tick, state_version=state.version)
        source.submit(plan)
        plan.irrigation.append(state.plots[0].id)
        received = await source.plan(state, [])
        assert received.irrigation == []
    asyncio.run(scenario())


def test_external_source_rejects_unknown_wire_fields() -> None:
    source = ExternalPlanSource(EventBus())
    with pytest.raises(ValidationError):
        source.submit({"tick": 0, "overwrite_resources": {"water": 0}})


def test_resource_edit_cancels_external_wait_and_new_plan_is_not_consumed_by_old_request() -> None:
    async def scenario():
        repo, bus = StateRepository(create_initial_state()), EventBus()
        source = ExternalPlanSource(bus)
        loop = WorldLoop(repo, bus, source)
        pending = asyncio.create_task(loop.tick())
        while not loop.planning:
            await asyncio.sleep(0)
        changed = await loop.edit_resources({"power": repo.get().resources["power"].value})
        source.submit(TickPlan(tick=changed.tick, state_version=changed.version))
        discarded = await asyncio.wait_for(pending, timeout=1)
        assert discarded.tick == changed.tick
        completed = await asyncio.wait_for(loop.tick(), timeout=1)
        assert completed.tick == changed.tick + 1
    asyncio.run(scenario())


def test_relay_thought_only_publishes_validated_message() -> None:
    async def scenario():
        bus = EventBus()
        queue = bus.subscribe()
        source = ExternalPlanSource(bus)
        thought = {"id": "external", "ts": 0, "tick": 0, "agent": "plant", "kind": "advice", "text": "Advice supplied by teammate"}
        await source.relay_thought(thought)
        message = queue.get_nowait()
        assert message["type"] == "agent_thought"
        assert message["payload"]["agent"] == "plant"
        with pytest.raises(ValidationError):
            await source.relay_thought({**thought, "resources": {"water": 0}})
        assert queue.empty()
    asyncio.run(scenario())
