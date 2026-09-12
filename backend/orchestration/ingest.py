"""Internal commit pipeline, never a public arbitrary state-patch API."""
from __future__ import annotations

from backend.domain.models import TickPlan, WorldEvent, WorldState
from backend.domain.state import StateRepository
from backend.orchestration.event_bus import EventBus


class Ingest:
    def __init__(self, repository: StateRepository, bus: EventBus):
        self.repository = repository
        self.bus = bus

    async def commit(self, state: WorldState, events: list[WorldEvent],
                     plan: TickPlan | None = None) -> None:
        """Called under the world lock with engine or control-service output.

        Resource edits must already have passed the dedicated engine edit path.
        This method performs no arithmetic and exposes no patch operation.
        """
        self.repository.set(state)
        for event in events:
            if event.type == "mission_failed":
                await self.bus.publish("mission_failed", {
                    "tick": event.tick,
                    "reason": event.detail.get("reason", state.failure_reason),
                    "deaths": event.detail.get("deaths", []),
                })
        if plan is not None:
            await self.bus.publish("tick_plan", plan)
        for event in events:
            await self.bus.publish("world_event", event)
        await self.bus.publish("state_update", self.repository.get())
