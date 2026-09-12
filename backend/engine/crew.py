from backend.domain.config import C, crew_consumption_per_tick
from backend.domain.models import Death, Refill
from backend.engine.events import emit


def check_deaths(state, summary, events):
    oxygen_empty = state.resources["oxygen"].value <= 0
    for crew in state.crew.values():
        if not crew.alive:
            continue
        reason = "oxygen" if oxygen_empty else ("food_energy" if crew.food_energy <= 0
                  else "water" if crew.water <= 0 else None)
        if reason:
            crew.alive = False
            crew.death_reason = reason
            crew.current_task = "dead"
            summary.deaths.append(Death(crew_id=crew.id, reason=reason))
            emit(state, events, "crew_died", crew.id, reason=reason)
    if summary.deaths and not state.failed:
        state.failed = True
        state.failure_reason = summary.deaths[0].reason
        emit(state, events, "mission_failed", reason=state.failure_reason,
             deaths=[death.model_dump() for death in summary.deaths])
    return state.failed


def refill(state, plan, summary):
    for request in plan.refills:
        crew = state.crew[request.crew_id]
        if not crew.alive:
            continue
        field = "food_energy" if request.kind == "food" else "water"
        resource = state.resources[request.kind]
        actual = min(request.amount, C["crew"][field]["refill_max"], resource.value,
                     C["crew"][field]["capacity"] - getattr(crew, field))
        actual = max(0, actual)
        resource.value -= actual
        setattr(crew, field, getattr(crew, field) + actual * C["crew"]["conversion"]["refill_ratio"])
        crew.current_task = "eating" if request.kind == "food" else "drinking"
        crew.location = "galley" if request.kind == "food" else "drinking_point_pending"
        summary.refills.append(Refill(crew_id=crew.id, kind=request.kind, amount=actual))


def consume_baseline(state, summary, events):
    consumption = crew_consumption_per_tick()
    alive_count = sum(crew.alive for crew in state.crew.values())
    for crew in state.crew.values():
        if not crew.alive:
            continue
        for field in ("food_energy", "water"):
            setattr(crew, field, max(0, getattr(crew, field) - consumption[field]))
            if check_deaths(state, summary, events):
                return
    state.resources["oxygen"].value = max(0, state.resources["oxygen"].value - consumption["oxygen"] * alive_count)
    check_deaths(state, summary, events)
