"""External agent boundary and clearly labelled recording playback; no LLM policy."""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any

from backend.domain.models import AgentThought, TickPlan, TickSummary, ValidationError, WorldEvent, WorldState


class ExternalPlanSource:
    def __init__(self, bus):
        self.bus = bus
        self._plans: deque = deque()
        self._available: asyncio.Event | None = None

    def submit(self, plan: TickPlan | dict[str, Any]) -> TickPlan:
        parsed = TickPlan.model_validate(plan).model_copy(deep=True)
        self._plans.append(parsed)
        if self._available is not None:
            self._available.set()
        return parsed.model_copy(deep=True)

    async def plan(self, state: WorldState, events: list[WorldEvent]) -> TickPlan:
        if self._available is None:
            self._available = asyncio.Event()
        while not self._plans:
            self._available.clear()
            await self._available.wait()
        return self._plans.popleft()

    def return_unused_plan(self, plan: TickPlan) -> None:
        self._plans.appendleft(plan.model_copy(deep=True))
        if self._available is not None:
            self._available.set()

    async def on_reset(self) -> None:
        self._plans.clear()

    async def relay_thought(self, thought: AgentThought | dict[str, Any]) -> AgentThought:
        parsed = AgentThought.model_validate(thought)
        await self.bus.publish("agent_thought", parsed.model_dump(mode="json"))
        return parsed

    async def validation_failed(self, state: WorldState, errors: list[ValidationError]) -> None:
        await self.relay_thought(AgentThought(
            id=str(uuid.uuid4()), ts=time.time(), tick=state.tick, agent="core", kind="validation_error",
            text="外部 TickPlan 未通過驗證，等待修正。",
            payload={"source": "validation_adapter", "errors": [error.model_dump() for error in errors]},
        ))


class MockPlanSource(ExternalPlanSource):
    """Replay the selected recording. Exhaustion pauses through the loop error path."""

    def __init__(self, bus, tape_path: str | Path | None = None):
        super().__init__(bus)
        path = Path(tape_path) if tape_path is not None else Path(__file__).resolve().parents[1] / "fixtures" / "plan_tape.json"
        self.tape = json.loads(path.read_text(encoding="utf-8"))
        if self.tape.get("mock") is not True:
            raise ValueError("Mock plan tape must be explicitly labelled mock")
        self._branch_started_tick: int | None = None
        self._seen_interventions: set[str] = set()
        self._entry: dict[str, Any] | None = None
        self._conversation_id: str | None = None
        self._message_ids: dict[str, str] = {}

    async def plan(self, state: WorldState, events: list[WorldEvent]) -> TickPlan:
        for event in events:
            if (event.type == "player_edit" and "power" in event.detail.get("values", {})
                    and event.id not in self._seen_interventions):
                self._seen_interventions.add(event.id)
                self._branch_started_tick = state.tick
        branch = self.tape["power_edit"]
        offset = state.tick - self._branch_started_tick if self._branch_started_tick is not None else len(branch)
        if 0 <= offset < len(branch):
            entry = branch[offset]
        else:
            if not 0 <= state.tick < len(self.tape["normal"]):
                raise RuntimeError("Mock recording exhausted; awaiting another recording or external agent")
            entry = self.tape["normal"][state.tick]
        self._entry = entry
        self._conversation_id = f"decision-{state.tick}"
        self._message_ids = {thought["local_id"]: str(uuid.uuid4()) for thought in entry["thoughts"] if "local_id" in thought}
        for thought in entry["thoughts"]:
            if thought["kind"] != "reflection":
                await self._emit_recorded(thought, state.tick)
        plan = TickPlan.model_validate(entry["plan"]).model_copy(deep=True)
        plan.tick = state.tick
        plan.state_version = state.version
        if not plan.rationale.startswith("[MOCK]"):
            plan.rationale = "[MOCK] " + plan.rationale
        return plan

    async def _emit_recorded(self, thought: dict[str, Any], tick: int, summary: TickSummary | None = None) -> None:
        payload = {"mock": True, "recorded": True}
        if isinstance(thought.get("payload"), dict):
            payload.update(thought["payload"])
        payload["mock"] = True
        payload.setdefault("conversation_id", self._conversation_id)
        payload.setdefault("sender", thought["agent"])
        payload.setdefault("avatar", thought["agent"])
        payload.setdefault("to", "core" if thought["agent"] != "core" else "all")
        payload.setdefault("reply_to", None)
        if isinstance(payload["reply_to"], str) and payload["reply_to"] in self._message_ids:
            payload["reply_to"] = self._message_ids[payload["reply_to"]]
        if isinstance(payload.get("in_reply_to"), list):
            payload["in_reply_to"] = [self._message_ids.get(item, item) for item in payload["in_reply_to"]]
        if summary is not None:
            payload["actual_summary"] = summary.model_dump(mode="json")
        await self.relay_thought(AgentThought(
            id=self._message_ids.get(thought.get("local_id"), str(uuid.uuid4())), ts=time.time(), tick=tick, agent=thought["agent"], kind=thought["kind"],
            text="[MOCK] " + thought["text"], payload=payload,
        ))

    async def validation_failed(self, state: WorldState, errors: list[ValidationError]) -> None:
        await self.relay_thought(AgentThought(
            id=str(uuid.uuid4()), ts=time.time(), tick=state.tick, agent="core", kind="validation_error",
            text="[MOCK] 預錄 TickPlan 未通過目前世界驗證。",
            payload={"mock": True, "errors": [error.model_dump() for error in errors]},
        ))

    async def post_settle(self, state: WorldState, summary: TickSummary, events: list[WorldEvent]) -> None:
        if self._entry is not None:
            for thought in self._entry["thoughts"]:
                if thought["kind"] == "reflection":
                    await self._emit_recorded(thought, state.tick, summary)

    async def on_reset(self) -> None:
        await super().on_reset()
        self._entry = None
        self._conversation_id = None
        self._message_ids.clear()
        self._branch_started_tick = None
        self._seen_interventions.clear()
