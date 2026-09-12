"""Deterministic events from one settlement; no clock, random IDs, or I/O."""
from backend.domain.models import WorldEvent


def emit(state, events, kind, target=None, **detail):
    events.append(WorldEvent(id=f"v{state.version}:t{state.tick}:e{len(events)}",
                             tick=state.tick, type=kind, target=target, detail=detail))
