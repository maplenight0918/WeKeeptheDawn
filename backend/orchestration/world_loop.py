"""Serialized world orchestration with an injected external plan source."""
from __future__ import annotations

import asyncio
import math
from typing import Protocol

from backend.domain.config import C
from backend.domain.models import TickPlan, WorldEvent, WorldState, create_initial_state
from backend.engine.world_engine import WorldEngine
from backend.orchestration.ingest import Ingest
from backend.orchestration.plan_validator import PlanValidator


class PlanSource(Protocol):
    async def plan(self, state: WorldState, events: list[WorldEvent]) -> TickPlan:
        """Return a teammate's plan or an explicitly identified mock response."""
        ...


class WorldLoop:
    def __init__(self, repository, bus, plan_source: PlanSource, *, decision_interval: int = 1):
        if isinstance(decision_interval, bool) or not isinstance(decision_interval, int) or decision_interval < 1:
            raise ValueError("decision_interval must be a positive integer")
        self.repository = repository
        self.bus = bus
        self.plan_source = plan_source
        self.decision_interval = decision_interval
        self.ingest = Ingest(repository, bus)
        self._lock = asyncio.Lock()
        self._tick_lock = asyncio.Lock()
        self._stop_event = asyncio.Event()
        self._state_changed = asyncio.Event()
        self._wake_event = asyncio.Event()
        self._runner = None
        self._force_decision = True
        self._events: list[WorldEvent] = []
        self.planning = False

    async def _request_plan(self, state, events):
        request = asyncio.create_task(self.plan_source.plan(state, events))
        changed = asyncio.create_task(self._state_changed.wait())
        try:
            await asyncio.wait({request, changed}, return_when=asyncio.FIRST_COMPLETED)
            if self._state_changed.is_set():
                # An edit and a just-submitted replacement can wake together.
                # Preserve a response explicitly bound to the new snapshot.
                if request.done() and not request.cancelled() and request.exception() is None:
                    unused = request.result()
                    current = self.repository.get()
                    if (isinstance(unused, TickPlan) and unused.state_version == current.version
                            and unused.tick == current.tick and hasattr(self.plan_source, "return_unused_plan")):
                        self.plan_source.return_unused_plan(unused)
                return None
            return await request
        finally:
            for task in (request, changed):
                if not task.done():
                    task.cancel()
            await asyncio.gather(request, changed, return_exceptions=True)

    async def tick(self) -> WorldState:
        # The task owns the complete planning/settlement cycle. A second caller
        # does not queue another elapsed tick while a remote source is waiting.
        if self._tick_lock.locked():
            return self.repository.get()
        async with self._tick_lock:
            async with self._lock:
                state = self.repository.get()
                if state.paused or state.paused_reason is not None or state.failed:
                    return state
                version = state.version
                self._state_changed.clear()
                decide = self._force_decision or bool(self._events) or state.tick % self.decision_interval == 0
                observed_events = list(self._events)
            rejected: list[WorldEvent] = []
            if decide:
                self.planning = True
                try:
                    for attempt in range(3):  # spec §5.3 validation attempts, not a world coefficient.
                        proposed = await self._request_plan(state.model_copy(deep=True), list(observed_events + rejected))
                        if proposed is None:
                            self._force_decision = True
                            return self.repository.get()
                        async with self._lock:
                            current = self.repository.get()
                            if current.version != version or current.paused or current.failed:
                                self._force_decision = True
                                return current
                        errors = PlanValidator.check(state, proposed)
                        if not errors:
                            plan = proposed if isinstance(proposed, TickPlan) else TickPlan.model_validate(proposed)
                            break
                        if hasattr(self.plan_source, "validation_failed"):
                            await self.plan_source.validation_failed(state, errors)
                        rejected.append(WorldEvent(
                            id=f"validation-{version}-{attempt}", tick=state.tick, type="plan_failed",
                            detail={"attempt": attempt + 1, "validation_errors": [error.model_dump() for error in errors], "retrying": True},
                        ))
                    else:
                        plan = TickPlan(tick=state.tick, state_version=version, rationale="Plan validation attempts exhausted")
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    async with self._lock:
                        current = self.repository.get()
                        if current.version != version:
                            self._force_decision = True
                            return current
                        current.paused = True
                        current.paused_reason = "error"
                        current.version += 1
                        failure = WorldEvent(id=f"source-error-{current.version}", tick=current.tick, type="plan_failed",
                                             detail={"reason": "plan_source_error", "error_type": type(exc).__name__})
                        self._force_decision = True
                        await self.ingest.commit(current, [failure])
                        return current
                finally:
                    self.planning = False
            else:
                plan = TickPlan(tick=state.tick, state_version=version,
                                generation=dict(state.settings.generation),
                                water_production_l=state.settings.water_production_l,
                                irrigation=list(state.settings.irrigation))

            async with self._lock:
                current = self.repository.get()
                if current.version != version or current.paused or current.paused_reason is not None or current.failed:
                    self._force_decision = True
                    return current
                try:
                    next_state, summary, events = WorldEngine.settle(current, plan)
                except Exception as exc:
                    # No partial projection is committed. Persistence errors in
                    # commit itself are deliberately allowed to surface.
                    current = self.repository.get()
                    current.paused = True
                    current.paused_reason = "error"
                    current.version += 1
                    failure = WorldEvent(id=f"engine-error-{current.version}", tick=current.tick,
                                         type="plan_failed", detail={"reason": "engine_error", "error_type": type(exc).__name__})
                    self._force_decision = True
                    await self.ingest.commit(current, [failure])
                    return current
                if rejected and len(rejected) == 3:
                    events.append(WorldEvent(id=f"plan-failed-{next_state.version}", tick=next_state.tick,
                                             type="plan_failed", detail={"attempts": len(rejected), "validation_errors": rejected[-1].detail["validation_errors"]}))
                self._events = list(events)
                self._force_decision = False
                await self.ingest.commit(next_state, events, plan=plan)
                if hasattr(self.plan_source, "post_settle"):
                    await self.plan_source.post_settle(next_state, summary, events)
                return next_state

    async def control(self, cmd: str, value: float | None = None) -> WorldState:
        async with self._lock:
            state = self.repository.get()
            if cmd == "pause":
                state.paused = True
                state.paused_reason = "player"
            elif cmd == "resume":
                if state.failed:
                    return state
                state.paused = False
                state.paused_reason = None
                self._force_decision = True
            elif cmd == "speed":
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                    raise ValueError("speed must be a positive finite number")
                state.speed = value
            else:
                raise ValueError("Unknown control command")
            state.version += 1
            self._state_changed.set()
            self._wake_event.set()
            await self.ingest.commit(state, [])
            return state

    async def decision_request(self):
        async with self._lock:
            state = self.repository.get()
            request = getattr(self.plan_source, "request", None)
            if (not request or state.paused or state.paused_reason is not None or state.failed
                    or (request["tick"], request["state_version"]) != (state.tick, state.version)):
                return None
            from copy import deepcopy
            return deepcopy(request)

    async def submit_decision(self, request_id, submission_id, plan):
        async with self._lock:
            return self.plan_source.submit_bound(request_id, submission_id, plan, self.repository.get())

    async def fail_decision(self, request_id):
        async with self._lock:
            self.plan_source.fail_bound(request_id, self.repository.get())

    async def edit_resources(self, values: dict[str, float]) -> WorldState:
        async with self._lock:
            state, events = WorldEngine.edit_resources(self.repository.get(), values)
            self._events.extend(events)
            self._force_decision = True
            self._state_changed.set()
            self._wake_event.set()
            await self.ingest.commit(state, events)
            return state

    async def reset(self) -> WorldState:
        async with self._lock:
            previous = self.repository.get()
            state = create_initial_state()
            state.version = previous.version + 1
            self._events = []
            self._force_decision = True
            self._state_changed.set()
            self._wake_event.set()
            await self.ingest.commit(state, [])
            if hasattr(self.plan_source, "on_reset"):
                await self.plan_source.on_reset()
            return state

    async def run(self) -> None:
        if self._runner is not None:
            raise RuntimeError("World loop is already running")
        self._runner = asyncio.current_task()
        self._stop_event.clear()
        try:
            while not self._stop_event.is_set():
                # Clear before work, never after it: a control request arriving
                # during settlement must wake the following delay.
                self._wake_event.clear()
                await self.tick()
                if self.repository.get().failed:
                    break
                delay = C["time"]["real_seconds_per_tick"] / self.repository.get().speed
                stopped = asyncio.create_task(self._stop_event.wait())
                woken = asyncio.create_task(self._wake_event.wait())
                try:
                    await asyncio.wait({stopped, woken}, timeout=delay, return_when=asyncio.FIRST_COMPLETED)
                finally:
                    for task in (stopped, woken):
                        if not task.done():
                            task.cancel()
                    await asyncio.gather(stopped, woken, return_exceptions=True)
        finally:
            self._runner = None

    async def stop(self) -> None:
        self._stop_event.set()
        if self._runner is not None and self._runner is not asyncio.current_task():
            self._runner.cancel()
            try:
                await self._runner
            except asyncio.CancelledError:
                pass
