"""Independent integration contract checks, without a game agent or LLM."""
import asyncio

import pytest
from pydantic import ValidationError

from backend.domain.config import C
from backend.domain.models import AgentThought, TickPlan, create_initial_state
from backend.domain.state import StateRepository
from backend.integration.sources import ExternalPlanSource
from backend.orchestration.event_bus import EventBus
from backend.orchestration.world_loop import WorldLoop


def setup_world():
    repository, bus = StateRepository(), EventBus()
    source = ExternalPlanSource(bus)
    return repository, bus, source, WorldLoop(repository, bus, source)


def test_external_wait_does_not_settle_or_accumulate_ticks():
    async def scenario():
        repo, _, source, loop = setup_world()
        before = repo.get().model_dump()
        pending = asyncio.create_task(loop.tick())
        try:
            await asyncio.sleep(0)
            assert not pending.done()
            for _ in range(5):
                concurrent = await loop.tick()
                assert concurrent.model_dump() == before
            assert repo.get().model_dump() == before
            state = repo.get()
            source.submit(TickPlan(tick=state.tick, state_version=state.version))
            settled = await asyncio.wait_for(pending, timeout=2)
            assert settled.tick == state.tick + 1
            assert settled.version == state.version + 1
        finally:
            if not pending.done():
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)

    asyncio.run(scenario())


def test_submitted_stale_plans_are_rejected_by_loop_without_applying_work():
    async def scenario():
        repo, bus, source, loop = setup_world()
        queue = bus.subscribe()
        state = repo.get()
        stale = TickPlan(tick=state.tick, state_version=state.version - 1,
                         generation={crew: C["generation"]["max_work_per_crew"] for crew in state.crew})
        for _ in range(3):
            source.submit(stale)
        result = await asyncio.wait_for(loop.tick(), timeout=2)
        assert result.tick == state.tick + 1
        assert result.last_summary.generation.actual == 0
        assert result.resources["power"].value == state.resources["power"].value
        messages = []
        while not queue.empty():
            messages.append(queue.get_nowait())
        failures = [m["payload"] for m in messages if m["type"] == "world_event"
                    and m["payload"]["type"] == "plan_failed"]
        assert failures
        assert any(error["code"] == "PLAN_STALE" for event in failures
                   for error in event["detail"].get("validation_errors", []))

    asyncio.run(scenario())


def test_thought_relay_is_display_only_even_when_payload_mentions_resources():
    async def scenario():
        repo, bus, source, _ = setup_world()
        queue = bus.subscribe()
        before = repo.get().model_dump()
        thought = AgentThought(id="external-observation", ts=0, tick=repo.get().tick,
                               agent="core", kind="observe", text="展示訊息沒有狀態寫入權限",
                               payload={"resources": {"oxygen": 0}, "action": "edit_resources"})
        relayed = await source.relay_thought(thought)
        assert relayed == thought
        assert queue.get_nowait() == {"type": "agent_thought", "payload": thought.model_dump(mode="json")}
        assert repo.get().model_dump() == before

    asyncio.run(scenario())


def test_unknown_agent_thought_field_is_rejected_without_broadcast():
    async def scenario():
        repo, bus, source, _ = setup_world()
        queue = bus.subscribe()
        before = repo.get().model_dump()
        with pytest.raises(ValidationError):
            await source.relay_thought({
                "id": "invalid", "ts": 0, "tick": 0, "agent": "core", "kind": "plan", "text": "x",
                "resources": {"oxygen": 0},
            })
        assert queue.empty()
        assert repo.get().model_dump() == before

    asyncio.run(scenario())


def test_submitted_plan_copies_caller_and_return_value():
    async def scenario():
        _, bus, source, _ = setup_world()
        state = create_initial_state()
        original = TickPlan(tick=state.tick, state_version=state.version,
                            irrigation=[state.plots[0].id])
        accepted = source.submit(original)
        original.irrigation.clear()
        accepted.irrigation.clear()
        queued = await source.plan(state, [])
        assert queued.irrigation == [state.plots[0].id]

    asyncio.run(scenario())
