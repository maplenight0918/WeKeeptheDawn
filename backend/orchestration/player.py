"""Pure player intervention adapter; orchestration later owns serialized commit."""
from __future__ import annotations

from backend.domain.models import WorldEvent, WorldState


def edit_resources(state: WorldState, values: dict[str, float]) -> tuple[WorldState, list[WorldEvent]]:
    from backend.engine.world_engine import WorldEngine

    return WorldEngine.edit_resources(state, values)
