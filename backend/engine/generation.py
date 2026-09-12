from backend.domain.config import C
from backend.engine.crew import check_deaths


def generate(state, plan, summary, events):
    constants = C["generation"]
    occupied = {request.crew_id for request in plan.refills} | {op.crew_id for op in plan.plot_ops}
    caps = {crew_id: min(request, constants["max_work_per_crew"],
                         state.crew[crew_id].food_energy / constants["food_energy_per_work"])
            for crew_id, request in plan.generation.items()
            if state.crew[crew_id].alive and crew_id not in occupied and request > 0}
    total = sum(caps.values())
    summary.generation.requested = sum(plan.generation.values())
    if total <= 0:
        return
    actual = min(total, state.resources["oxygen"].value / constants["oxygen_per_work"],
                 (state.resources["power"].capacity - state.resources["power"].value) / constants["power_per_work"])
    # Guide §2.4 defines simultaneous proportional allocation, not a crew policy.
    for crew_id, cap in caps.items():
        crew = state.crew[crew_id]
        work = actual * cap / total
        crew.work_this_tick = work
        crew.current_task = "generating"
        crew.location = "power_bay"
        crew.food_energy = max(0, crew.food_energy - work * constants["food_energy_per_work"])
    summary.generation.actual = actual
    summary.generation.oxygen_used = actual * constants["oxygen_per_work"]
    summary.generation.power_out = actual * constants["power_per_work"]
    state.resources["oxygen"].value = max(0, state.resources["oxygen"].value - summary.generation.oxygen_used)
    state.resources["power"].value += summary.generation.power_out
    check_deaths(state, summary, events)
