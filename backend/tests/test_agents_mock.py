"""Mock transport integration only: no game agent or LLM strategy is implemented."""
from __future__ import annotations

import asyncio

from backend.domain.models import create_initial_state
from backend.domain.state import StateRepository
from backend.integration.sources import MockPlanSource
from backend.orchestration.event_bus import EventBus
from backend.orchestration.plan_validator import PlanValidator
from backend.orchestration.world_loop import WorldLoop


def test_mock_recording_complete_decision_has_ordered_thoughts_and_valid_plan() -> None:
    async def scenario():
        repo, bus = StateRepository(create_initial_state()), EventBus()
        queue = bus.subscribe()
        source = MockPlanSource(bus)
        before = repo.get()
        loop = WorldLoop(repo, bus, source)
        after = await loop.tick()
        messages = []
        while not queue.empty():
            messages.append(queue.get_nowait())
        thoughts = [message["payload"] for message in messages if message["type"] == "agent_thought"]
        assert [thought["kind"] for thought in thoughts] == ["observe", "risk", "advice", "advice", "plan", "reflection"]
        assert {thought["agent"] for thought in thoughts if thought["kind"] == "advice"} == {"plant", "human"}
        plan = next(message["payload"] for message in messages if message["type"] == "tick_plan")
        assert PlanValidator.check(before, plan) == []
        assert after.tick == before.tick + 1
        assert all(thought["payload"]["mock"] for thought in thoughts)
        assert {thought["payload"]["conversation_id"] for thought in thoughts} == {f"decision-{before.tick}"}
        assert all(thought["payload"]["sender"] == thought["agent"] for thought in thoughts)
        assert all("avatar" in thought["payload"] and "to" in thought["payload"] for thought in thoughts)
        assert thoughts[-1]["payload"]["actual_summary"] == after.last_summary.model_dump(mode="json")
        types = [message["type"] for message in messages]
        assert types.index("state_update") < len(types) - 1
        assert messages[-1]["payload"]["kind"] == "reflection"
    asyncio.run(scenario())


def test_mock_preserves_conversation_payload_and_resolves_reply_ids() -> None:
    async def scenario():
        bus = EventBus()
        queue = bus.subscribe()
        source = MockPlanSource(bus)
        state = create_initial_state()
        entry = source.tape["normal"][state.tick]
        entry["thoughts"][0]["local_id"] = "observation"
        entry["thoughts"][1]["payload"] = {"reply_to": "observation", "to": "plant,human", "extra": "preserved"}
        await source.plan(state, [])
        observation = queue.get_nowait()["payload"]
        risk = queue.get_nowait()["payload"]
        assert risk["payload"]["reply_to"] == observation["id"]
        assert risk["payload"]["extra"] == "preserved"
        assert risk["payload"]["to"] == "plant,human"
    asyncio.run(scenario())


def test_mock_uses_recorded_plan_even_if_resources_change_without_event() -> None:
    async def scenario():
        source = MockPlanSource(EventBus())
        state = create_initial_state()
        recorded = await source.plan(state, [])
        state.resources["power"].value = 0
        state.resources["water"].value = 0
        replayed = await source.plan(state, [])
        assert recorded == replayed
    asyncio.run(scenario())


def test_power_edit_replays_partial_then_recovered_recording() -> None:
    async def scenario():
        repo, bus = StateRepository(create_initial_state()), EventBus()
        source = MockPlanSource(bus)
        loop = WorldLoop(repo, bus, source)
        # Fixture scenario input; amounts are not world coefficients or strategy.
        await loop.edit_resources({"power": 300})
        partial = await loop.tick()
        partial_again = await loop.tick()
        recovered = await loop.tick()
        assert partial.settings.irrigation == source.tape["power_edit"][0]["plan"]["irrigation"]
        assert partial_again.settings.irrigation == source.tape["power_edit"][1]["plan"]["irrigation"]
        assert recovered.settings.irrigation == source.tape["power_edit"][2]["plan"]["irrigation"]
        assert any(plot.consecutive_unirrigated_ticks for plot in partial.plots)
        assert not any(plot.consecutive_unirrigated_ticks for plot in recovered.plots)
        assert not recovered.failed
    asyncio.run(scenario())
