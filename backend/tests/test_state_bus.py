"""Isolation, fan-out and failure-order contracts for orchestration."""
import asyncio

import pytest

from backend.domain.models import TickPlan, create_initial_state
from backend.domain.state import StateRepository
from backend.engine.world_engine import WorldEngine
from backend.orchestration.event_bus import EventBus
from backend.orchestration.ingest import Ingest


def test_repository_copies_constructor_get_and_set():
    initial = create_initial_state()
    repo = StateRepository(initial)
    original = repo.get().model_dump()
    initial.resources["water"].value = 0
    fetched = repo.get()
    fetched.resources["water"].value = 0
    assert repo.get().model_dump() == original
    fetched.version += 1
    repo.set(fetched)
    stored = repo.get().model_dump()
    fetched.resources["food"].value = 0
    assert repo.get().model_dump() == stored


def test_persist_callback_cannot_mutate_stored_snapshot():
    saved = []

    def persist(snapshot):
        saved.append(snapshot.model_dump())
        snapshot.resources["water"].value = 0

    state = create_initial_state()
    repo = StateRepository(persist=persist)
    repo.set(state)
    assert saved == [state.model_dump()]
    assert repo.get().model_dump() == state.model_dump()


def test_persist_failure_does_not_commit_or_publish():
    def persist(snapshot):
        raise OSError("fixture persistence failure")

    async def scenario():
        repo = StateRepository(persist=persist)
        bus = EventBus()
        queue = bus.subscribe()
        original = repo.get().model_dump()
        modified = repo.get()
        modified.version += 1
        with pytest.raises(OSError):
            await Ingest(repo, bus).commit(modified, [])
        assert repo.get().model_dump() == original
        assert queue.empty()

    asyncio.run(scenario())


def test_bus_fans_out_isolated_envelopes_and_preserves_order():
    async def scenario():
        bus = EventBus()
        a, b = bus.subscribe(), bus.subscribe()
        payload = {"nested": {"value": "original"}}
        await bus.publish("one", payload)
        payload["nested"]["value"] = "mutated caller"
        await bus.publish("two", {})
        first = a.get_nowait()
        first["payload"]["nested"]["value"] = "mutated subscriber"
        assert b.get_nowait() == {"type": "one", "payload": {"nested": {"value": "original"}}}
        assert a.get_nowait()["type"] == b.get_nowait()["type"] == "two"

    asyncio.run(scenario())


def test_bus_unsubscribe_is_idempotent_and_disconnect_stops_delivery():
    async def scenario():
        bus = EventBus()
        departed, active = bus.subscribe(), bus.subscribe()
        bus.unsubscribe(departed)
        bus.unsubscribe(departed)
        assert bus.subscriber_count == 1
        await bus.publish("state_update", create_initial_state())
        assert departed.empty()
        assert active.get_nowait()["payload"]["tick"] == 0
        bus.unsubscribe(active)
        assert bus.subscriber_count == 0

    asyncio.run(scenario())


def test_bus_records_serialized_payload_even_without_subscribers():
    async def scenario():
        recorded = []

        def record(kind, payload):
            recorded.append((kind, payload.copy()))
            payload["tick"] = "callback cannot affect delivery"

        state = create_initial_state()
        bus = EventBus(record=record)
        await bus.publish("state_update", state)
        assert recorded == [("state_update", state.model_dump(mode="json"))]
        queue = bus.subscribe()
        await bus.publish("state_update", state)
        assert queue.get_nowait()["payload"]["tick"] == state.tick

    asyncio.run(scenario())


def test_ingest_commits_failure_before_broadcast_and_sends_failure_first():
    async def scenario():
        state = create_initial_state()
        failed, events = WorldEngine.edit_resources(state, {"oxygen": 0})
        repo, bus = StateRepository(state), EventBus()
        a, b = bus.subscribe(), bus.subscribe()
        await Ingest(repo, bus).commit(failed, events)
        assert repo.get().failed
        for queue in (a, b):
            first = queue.get_nowait()
            assert first["type"] == "mission_failed"
            assert first["payload"]["reason"] == "oxygen"
            assert first["payload"]["deaths"]
            remaining = []
            while not queue.empty():
                remaining.append(queue.get_nowait())
            assert remaining[-1]["type"] == "state_update"
            assert remaining[-1]["payload"] == failed.model_dump(mode="json")

    asyncio.run(scenario())


def test_ingest_emits_optional_plan_without_reapplying_settlement():
    async def scenario():
        state = create_initial_state()
        plan = TickPlan(tick=state.tick)
        settled, _, events = WorldEngine.settle(state, plan)
        repo, bus = StateRepository(state), EventBus()
        queue = bus.subscribe()
        await Ingest(repo, bus).commit(settled, events, plan)
        assert queue.get_nowait() == {"type": "tick_plan", "payload": plan.model_dump(mode="json")}
        assert repo.get().model_dump() == settled.model_dump()

    asyncio.run(scenario())
