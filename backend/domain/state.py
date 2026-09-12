"""Authoritative snapshot storage; the world loop owns serialization."""
from __future__ import annotations

from collections.abc import Callable

from backend.domain.models import WorldState, create_initial_state


class StateRepository:
    def __init__(self, initial: WorldState | None = None,
                 persist: Callable[[WorldState], None] | None = None):
        self._state = (initial if initial is not None else create_initial_state()).model_copy(deep=True)
        self._persist = persist

    def get(self) -> WorldState:
        return self._state.model_copy(deep=True)

    def set(self, state: WorldState) -> None:
        """Store an already settled snapshot, after successful persistence.

        Never use this method to implement resource arithmetic. The optional
        synchronous callback receives its own copy and may raise to abort commit.
        """
        snapshot = state.model_copy(deep=True)
        if self._persist is not None:
            self._persist(snapshot.model_copy(deep=True))
        self._state = snapshot
