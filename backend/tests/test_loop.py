from __future__ import annotations

import asyncio

import pytest

from backend.domain.config import C, CROPS
from backend.domain.models import PlotOp, Refill, TickPlan, create_initial_state
from backend.domain.state import StateRepository
from backend.orchestration.event_bus import EventBus
from backend.orchestration.world_loop import WorldLoop


class ScriptedSource:
    def __init__(self, invalid: bool = False):
        self.calls = 0
        self.invalid = invalid
        self.events = []

    async def plan(self, state, events):
        self.calls += 1
        self.events.append(events)
        return TickPlan(tick=state.tick, state_version=state.version,
                        water_production_l=-C["water_plant"]["max_l_per_tick"] if self.invalid else 0,
                        irrigation=[plot.id for plot in state.plots])


def test_pause_five_ticks_leaves_inventory_and_irrigation_unchanged() -> None:
    async def scenario():
        repo, bus, source = StateRepository(create_initial_state()), EventBus(), ScriptedSource()
        loop = WorldLoop(repo, bus, source)
        await loop.control("pause")
        before = repo.get().model_dump()
        for _ in range(5):
            await loop.tick()
        assert repo.get().model_dump() == before
        assert source.calls == 0
    asyncio.run(scenario())


def test_three_invalid_plans_settle_empty_plan_and_emit_plan_failed() -> None:
    async def scenario():
        repo, bus, source = StateRepository(create_initial_state()), EventBus(), ScriptedSource(invalid=True)
        queue = bus.subscribe()
        loop = WorldLoop(repo, bus, source)
        state = await loop.tick()
        assert source.calls == 3
        assert state.tick == 1
        assert all(plot.consecutive_unirrigated_ticks == C["irrigation"]["warning_after_ticks"] for plot in state.plots)
        assert state.settings.irrigation == []
        messages = []
        while not queue.empty():
            messages.append(queue.get_nowait())
        assert any(message["type"] == "world_event" and message["payload"]["type"] == "plan_failed" for message in messages)
        assert source.events[-1][-1].detail["validation_errors"][0]["code"] == "WATER_REQUEST_NEGATIVE"
    asyncio.run(scenario())


def test_continuous_settings_do_not_replay_one_shot_refills() -> None:
    class Source:
        calls = 0

        async def plan(self, state, events):
            self.calls += 1
            return TickPlan(tick=state.tick, irrigation=[plot.id for plot in state.plots], plot_ops=[
                PlotOp(order=0, crew_id=list(state.crew)[1], plot_id=state.plots[0].id, op="harvest")
            ], refills=[
                Refill(crew_id=next(iter(state.crew)), kind="food", amount=C["crew"]["food_energy"]["refill_max"])
            ])

    async def scenario():
        initial_state = create_initial_state()
        initial_state.plots[0].mature = True
        initial_state.plots[0].progress_ticks = CROPS[initial_state.plots[0].crop]["maturity_ticks"]
        repo, bus, source = StateRepository(initial_state), EventBus(), Source()
        loop = WorldLoop(repo, bus, source, decision_interval=5)
        initial = await loop.tick()
        next_state = await loop.tick()
        assert source.calls == 1
        assert initial.last_summary.refills
        assert next_state.last_summary.refills == []
        assert initial.last_summary.harvested
        assert next_state.last_summary.harvested == []
        assert next_state.settings.irrigation == initial.settings.irrigation
        assert next_state.resources["food"].value == initial.resources["food"].value + initial.pending_food
    asyncio.run(scenario())


def test_source_exception_enters_error_pause_without_settlement() -> None:
    class Source:
        async def plan(self, state, events):
            raise RuntimeError("simulated transport failure")

    async def scenario():
        repo = StateRepository(create_initial_state())
        before = repo.get()
        loop = WorldLoop(repo, EventBus(), Source())
        after = await loop.tick()
        assert after.paused and after.paused_reason == "error"
        assert after.tick == before.tick
        assert after.resources == before.resources
        assert after.plots == before.plots
        assert (await loop.tick()) == after
    asyncio.run(scenario())


def test_speed_control_changes_no_resources_or_tick() -> None:
    async def scenario():
        repo = StateRepository(create_initial_state())
        loop = WorldLoop(repo, EventBus(), ScriptedSource())
        before = repo.get()
        after = await loop.control("speed", 5)
        assert after.speed == 5
        assert after.tick == before.tick
        assert after.resources == before.resources
    asyncio.run(scenario())


def test_runner_wakes_for_pause_and_speed_control() -> None:
    class Source:
        def __init__(self):
            self.calls = 0
            self.first_plan = asyncio.Event()

        async def plan(self, state, events):
            self.calls += 1
            self.first_plan.set()
            return TickPlan(tick=state.tick, state_version=state.version)

    async def scenario():
        source = Source()
        loop = WorldLoop(StateRepository(create_initial_state()), EventBus(), source)
        runner = asyncio.create_task(loop.run())
        await source.first_plan.wait()
        while loop.repository.get().tick < 1:
            await asyncio.sleep(0)
        await loop.control("pause")
        paused = loop.repository.get().model_dump()
        # The runner consumes the wake signal immediately instead of sleeping
        # for its previous real-time interval, then it must not settle again.
        for _ in range(10):
            await asyncio.sleep(0)
        assert not loop._wake_event.is_set()
        assert loop.repository.get().model_dump() == paused
        await loop.control("speed", 20)
        for _ in range(10):
            await asyncio.sleep(0)
        assert loop.repository.get().speed == 20
        assert loop.repository.get().tick == paused["tick"]
        await loop.stop()
        assert runner.done()
    asyncio.run(scenario())


def test_runner_can_be_stopped_while_source_is_waiting() -> None:
    class Source:
        def __init__(self):
            self.entered = asyncio.Event()

        async def plan(self, state, events):
            self.entered.set()
            await asyncio.Event().wait()

    async def scenario():
        source = Source()
        loop = WorldLoop(StateRepository(create_initial_state()), EventBus(), source)
        runner = asyncio.create_task(loop.run())
        await source.entered.wait()
        await loop.stop()
        assert runner.done()
        assert not loop.planning
        assert loop.repository.get().tick == 0
    asyncio.run(scenario())


def test_engine_exception_enters_error_pause_without_partial_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.engine.world_engine import WorldEngine

    def broken_settle(state, plan):
        state.resources["water"].value = 0
        raise RuntimeError("simulated settlement failure")

    monkeypatch.setattr(WorldEngine, "settle", broken_settle)

    async def scenario():
        repo = StateRepository(create_initial_state())
        before = repo.get()
        loop = WorldLoop(repo, EventBus(), ScriptedSource())
        after = await loop.tick()
        assert after.paused and after.paused_reason == "error"
        assert after.tick == before.tick
        assert after.resources == before.resources
        assert after.plots == before.plots
        assert repo.get() == after
    asyncio.run(scenario())
