"""Calls the teammate's CoreAgent. Holds handoff context, never executes future stages."""
from __future__ import annotations

from collections import deque
from copy import deepcopy
from dataclasses import dataclass

from backend.domain.models import TickPlan
from agent_runner.contracts import ThoughtMapper, core_snapshot, current_tick_plan, game_rules


@dataclass
class Decision:
    plan: TickPlan
    conversation_id: str
    core_plan: dict


class CorePort:
    def __init__(self, core, *, mock=False):
        self.core, self.mock = core, mock
        self.rules = game_rules()
        self.history = deque(maxlen=24)
        self.current_plan = None

    async def decide(self, state, errors, emit):
        mapper = ThoughtMapper(state, mock=self.mock)
        snapshot = core_snapshot(state, self.rules)
        history = deepcopy(list(self.history))
        if errors:
            history.append({"type": "validation_error", "tick": state.tick,
                            "state_version": state.version, "errors": deepcopy(errors)})
        result = await self.core.plan(snapshot, self.rules, reason="validation_error" if errors else "decision_tick",
                                      history=history, current_plan=deepcopy(self.current_plan),
                                      on_event=lambda message: emit(mapper.map(message)))
        return Decision(current_tick_plan(result.plan, snapshot), result.discussion_id, deepcopy(result.plan))

    async def accept_result(self, decision, state, events, executed_plan=None):
        result = {"type": "settlement", "conversation_id": decision.conversation_id,
                  "input_tick": decision.plan.tick, "state_version": decision.plan.state_version,
                  "actual_summary": state.last_summary.model_dump(mode="json"),
                  "events": deepcopy(events), "world_version": state.version,
                  "executed_plan": (executed_plan or decision.plan).model_dump(mode="json")}
        self.history.append(result)
        self.current_plan = (None if any(event.get("type") == "plan_failed" for event in events)
                             else deepcopy(decision.core_plan))
        # The delivered CoreAgent has no reflection API. Keep the actual result as
        # its next planning input; don't generate a fake Core reflection here.

    def reset(self):
        self.history.clear()
        self.current_plan = None
