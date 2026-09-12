"""HTTP/WebSocket bridge. All mutations use the game's public API."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from uuid import uuid4

import httpx
from websockets.asyncio.client import connect

from backend.domain.models import AgentThought, TickPlan, WorldState

log = logging.getLogger(__name__)


def failure_codes(exc):
    """Allowlisted diagnostics only: never emit exception text, bodies or URLs."""
    from urllib.error import HTTPError, URLError
    from agent_runner.specialist_http import SpecialistFailure
    codes, seen = [], set()
    while exc is not None and id(exc) not in seen and len(codes) < 8:
        seen.add(id(exc))
        if isinstance(exc, SpecialistFailure):
            codes.extend(exc.codes)
        elif isinstance(exc, (HTTPError, httpx.HTTPStatusError)):
            status = exc.code if isinstance(exc, HTTPError) else exc.response.status_code
            codes.append(f"http_{status}")
        elif isinstance(exc, (TimeoutError, httpx.TimeoutException)):
            codes.append("timeout")
        elif isinstance(exc, (URLError, httpx.TransportError)):
            codes.append("transport_error")
        else:
            codes.append("planning_error")
        exc = exc.__cause__ or (None if exc.__suppress_context__ else exc.__context__)
    return codes


class StaleDecision(Exception):
    pass


class SettlementTracker:
    def __init__(self, plan):
        self.plan = plan
        self.observed_plan = None
        self.events = []
        self.state = None
        self.stale = False

    def accept(self, kind, payload):
        if kind == "tick_plan":
            plan = TickPlan.model_validate(payload)
            self.observed_plan = (plan if (plan.tick, plan.state_version) ==
                                  (self.plan.tick, self.plan.state_version) else None)
            self.events = []
        elif kind == "world_event" and self.observed_plan is not None:
            self.events.append(payload)
        elif kind == "state_update":
            state = WorldState.model_validate(payload)
            if (self.observed_plan is not None and state.tick == self.plan.tick + 1
                    and state.version == self.plan.state_version + 1
                    and state.last_summary is not None and state.last_summary.tick == state.tick):
                self.state = state
            elif state.version > self.plan.state_version:
                self.stale = True
            self.observed_plan = None if self.state is None else self.observed_plan


class AgentBridge:
    def __init__(self, core, base_url, *, client=None, poll_seconds=0.1):
        self.core = core
        self.base_url = base_url.rstrip("/")
        self.client = client or httpx.AsyncClient(base_url=self.base_url, timeout=10)
        self.owns_client = client is None
        self.poll_seconds = poll_seconds
        self.state = None
        self.changed = asyncio.Event()
        self.tracker = None
        self.pending = None
        self.completed = 0

    async def _read(self, socket):
        async for raw in socket:
            envelope = json.loads(raw)
            kind, payload = envelope["type"], envelope["payload"]
            if self.tracker:
                self.tracker.accept(kind, payload)
            if kind == "state_update":
                state = WorldState.model_validate(payload)
                if self.state is None or state.version > self.state.version:
                    if self.state is not None and state.tick < self.state.tick:
                        self.core.reset()
                    self.state = state
                    self.changed.set()
        raise ConnectionError("world stream closed")

    async def _get(self, path):
        response = await self.client.get(path)
        response.raise_for_status()
        return response.json()

    async def _thought(self, thought):
        response = await self.client.post("/ingest/thought", json=thought.model_dump(mode="json"))
        response.raise_for_status()

    async def _notice(self, state, text, *, conversation_id=None, **payload):
        await self._thought(AgentThought(
            id=str(uuid4()), ts=time.time(), tick=state.tick, agent="core", kind="observe", text=text,
            payload={"source": "bridge_result", "world_version": state.version,
                     "conversation_id": conversation_id or f"bridge-{state.version}",
                     "mock": self.core.mock, **payload},
        ))

    async def _decide(self, state, errors):
        queue = asyncio.Queue()

        async def relay():
            while True:
                thought = await queue.get()
                try:
                    if self.state.version != state.version:
                        raise StaleDecision()
                    await self._thought(thought)
                finally:
                    queue.task_done()

        self.changed.clear()
        planning = asyncio.create_task(self.core.decide(state, errors, queue.put_nowait))
        sender = asyncio.create_task(relay())
        changed = asyncio.create_task(self.changed.wait())
        try:
            done, _ = await asyncio.wait({planning, sender, changed}, return_when=asyncio.FIRST_COMPLETED)
            if changed in done and self.state.version != state.version:
                raise StaleDecision()
            if sender in done:
                sender.result()
            result = await planning
            # Don't let a failed relay strand queue.join().
            drained = asyncio.create_task(queue.join())
            try:
                done, _ = await asyncio.wait({drained, sender, changed}, return_when=asyncio.FIRST_COMPLETED)
                if sender in done:
                    sender.result()
                if changed in done and self.state.version != state.version:
                    raise StaleDecision()
                await drained
            finally:
                drained.cancel()
                await asyncio.gather(drained, return_exceptions=True)
            return result
        finally:
            for task in (planning, sender, changed):
                task.cancel()
            await asyncio.gather(planning, sender, changed, return_exceptions=True)

    async def _submit(self, request, decision):
        body = {"request_id": request["request_id"], "submission_id": str(uuid4()),
                "plan": decision.plan.model_dump(mode="json")}
        # This retry is ONLY for the new idempotent endpoint, same identity/body.
        for attempt in range(2):
            try:
                return await self.client.post("/ingest/decision-plan", json=body)
            except httpx.TransportError:
                if attempt:
                    return None  # unknown; wait for WS evidence, never send another plan

    async def _cycle(self, request, state):
        try:
            decision = await self._decide(state, request["validation_errors"])
        except StaleDecision:
            return
        except Exception as exc:
            # The backend checks identity/version and performs error pause under its lock.
            codes = failure_codes(exc)
            log.warning("Core planning failed: %s", codes)
            response = await self.client.post("/ingest/decision-failure", json={"request_id": request["request_id"]})
            if response.status_code not in (202, 409):
                response.raise_for_status()
            if response.status_code == 202:
                await self._notice(state, "[Bridge] 本輪規劃失敗，已通知後端錯誤暫停；未提交替代計畫。錯誤分類：" + " → ".join(codes),
                                   status="error", error_codes=codes, request_id=request["request_id"])
            return
        current = WorldState.model_validate(await self._get("/world"))
        if current.version != state.version or current.paused or current.paused_reason is not None or current.failed:
            return
        self.pending = decision
        self.tracker = SettlementTracker(decision.plan)
        response = await self._submit(request, decision)
        if response is not None and response.status_code == 409:
            self.pending = self.tracker = None
            return
        if response is not None and response.status_code == 422:
            # Schema errors did not enter the queue or consume a validator attempt.
            # Preserve structured errors for a fresh Core call on the same request.
            errors = response.json().get("detail", [])
            self.pending = self.tracker = None
            return errors
        if response is not None:
            response.raise_for_status()
        while True:
            if self.tracker.state is not None:
                settled = self.tracker.state
                await self.core.accept_result(decision, settled, self.tracker.events, self.tracker.observed_plan)
                await self._notice(
                    settled, "[Bridge] 已確認後端結算，實際摘要已交回 Core；這不是 Core 反思。",
                    conversation_id=decision.conversation_id,
                    input_tick=decision.plan.tick, input_state_version=decision.plan.state_version,
                    actual_summary=settled.last_summary.model_dump(mode="json"),
                    executed_plan=self.tracker.observed_plan.model_dump(mode="json"),
                    status="confirmed", events=self.tracker.events,
                )
                self.completed += 1
                self.pending = self.tracker = None
                return
            if self.tracker.stale:
                self.pending = self.tracker = None
                return
            next_request = await self._get("/decision")
            if next_request and next_request["request_id"] != request["request_id"]:
                # Validator rejected this attempt. Third rejection instead commits
                # an empty plan; re-check WS evidence after the HTTP await.
                if self.tracker.state is not None:
                    continue
                self.pending = self.tracker = None
                return
            await asyncio.sleep(self.poll_seconds)

    async def _work(self, max_ticks):
        schema_errors = {}
        schema_attempts = {}
        while max_ticks is None or self.completed < max_ticks:
            request = await self._get("/decision")
            if request and request["status"] == "awaiting" and self.state is not None:
                state = WorldState.model_validate(await self._get("/world"))
                if (state.tick, state.version) == (request["tick"], request["state_version"]):
                    if not state.paused and state.paused_reason is None and not state.failed:
                        request["validation_errors"] += schema_errors.pop(request["request_id"], [])
                        errors = await self._cycle(request, state)
                        if errors:
                            identity = request["request_id"]
                            schema_attempts[identity] = schema_attempts.get(identity, 0) + 1
                            if schema_attempts[identity] >= 3:
                                response = await self.client.post("/ingest/decision-failure", json={"request_id": identity})
                                if response.status_code not in (202, 409):
                                    response.raise_for_status()
                            else:
                                schema_errors[identity] = errors
                        else:
                            schema_attempts.pop(request["request_id"], None)
            await asyncio.sleep(self.poll_seconds)

    async def run(self, *, max_ticks=None):
        health = await self._get("/healthz")
        if health["mode"] != "external":
            raise ValueError("bridge requires external game mode")
        url = self.base_url.replace("https://", "wss://", 1).replace("http://", "ws://", 1) + "/ws"
        try:
            async with connect(url) as socket:
                reader = asyncio.create_task(self._read(socket))
                worker = asyncio.create_task(self._work(max_ticks))
                try:
                    done, _ = await asyncio.wait({reader, worker}, return_when=asyncio.FIRST_COMPLETED)
                    for task in done:
                        task.result()
                finally:
                    for task in (reader, worker):
                        task.cancel()
                    await asyncio.gather(reader, worker, return_exceptions=True)
                    if self.pending is not None:
                        log.warning("Settlement unconfirmed; no reflection or automatic resubmission")
                        try:
                            await self._notice(self.state, "[Bridge] 連線中斷，計畫結果未確認。",
                                               conversation_id=self.pending.conversation_id, status="unconfirmed")
                        except httpx.HTTPError:
                            pass
        finally:
            if self.owns_client:
                await self.client.aclose()
