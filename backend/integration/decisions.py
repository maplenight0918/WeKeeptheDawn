"""Version-bound external requests. No world writes or fallback decisions."""
from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from copy import deepcopy
from uuid import uuid4

from backend.integration.sources import ExternalPlanSource


class DecisionConflict(ValueError):
    pass


class ExternalDecisionFailed(RuntimeError):
    pass


class ManagedExternalPlanSource(ExternalPlanSource):
    def __init__(self, bus, *, timeout_seconds=420):
        super().__init__(bus)
        self.timeout_seconds = timeout_seconds
        self.request = None
        self.last_request = None
        self._failure = None
        self._receipts = OrderedDict()

    async def plan(self, state, events):
        request = {"request_id": str(uuid4()), "tick": state.tick,
                   "state_version": state.version, "status": "awaiting",
                   "deadline_ts": time.time() + self.timeout_seconds,
                   "validation_errors": [error for event in events
                       for error in event.detail.get("validation_errors", [])]}
        self.request = request
        self._failure = asyncio.get_running_loop().create_future()
        queued = asyncio.create_task(super().plan(state, events))
        try:
            done, _ = await asyncio.wait({queued, self._failure},
                                        timeout=self.timeout_seconds,
                                        return_when=asyncio.FIRST_COMPLETED)
            if not done:
                raise TimeoutError("external decision deadline exceeded")
            if self._failure in done:
                raise ExternalDecisionFailed("external decision failed")
            return queued.result()
        finally:
            self.last_request = deepcopy(request)
            self.request = None
            if not queued.done():
                queued.cancel()
            await asyncio.gather(queued, return_exceptions=True)
            if not self._failure.done():
                self._failure.cancel()

    def submit_bound(self, request_id, submission_id, plan, state):
        body = plan.model_dump(mode="json")
        prior = self._receipts.get(submission_id)
        if prior is not None:
            if prior[0] != (request_id, body):
                raise DecisionConflict("submission_id already used with different content")
            return {**prior[1], "duplicate": True}
        self._check(request_id, state)
        if (plan.tick, plan.state_version) != (state.tick, state.version):
            raise DecisionConflict("plan does not match observed tick/version")
        self.submit(plan)
        self.request["status"] = "queued"
        receipt = {"accepted": True, "validated": False, "duplicate": False,
                   "request_id": request_id, "submission_id": submission_id,
                   "tick": plan.tick, "state_version": plan.state_version}
        self._receipts[submission_id] = ((request_id, body), receipt)
        while len(self._receipts) > 256:
            self._receipts.popitem(last=False)
        return receipt

    def _check(self, request_id, state):
        if (not self.request or self.request["request_id"] != request_id
                or self.request["status"] != "awaiting"
                or (self.request["tick"], self.request["state_version"]) != (state.tick, state.version)
                or state.paused or state.paused_reason is not None or state.failed
                or time.time() >= self.request["deadline_ts"]):
            raise DecisionConflict("decision request is no longer awaiting this world version")

    def fail_bound(self, request_id, state):
        self._check(request_id, state)
        self.request["status"] = "failed"
        self._failure.set_result(True)

    async def validation_failed(self, state, errors):
        from backend.domain.models import AgentThought
        await self.relay_thought(AgentThought(
            id=str(uuid4()), ts=time.time(), tick=state.tick, agent="core",
            kind="validation_error", text="外部 TickPlan 未通過驗證，等待 Core 修正。",
            payload={"source": "validation_adapter", "world_version": state.version,
                     "request_id": (self.last_request or {}).get("request_id"),
                     "errors": [error.model_dump() for error in errors]},
        ))
