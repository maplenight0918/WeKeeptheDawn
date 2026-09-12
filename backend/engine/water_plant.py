from backend.domain.config import C
from backend.engine.crew import check_deaths


def produce_water(state, plan, summary, events):
    constants = C["water_plant"]
    summary.water_plant.requested = plan.water_production_l
    actual = min(plan.water_production_l, constants["max_l_per_tick"],
                 state.resources["power"].value / constants["power_per_l"],
                 state.resources["oxygen"].value / constants["oxygen_per_l"],
                 state.resources["water"].capacity - state.resources["water"].value)
    actual = max(0, actual)
    summary.water_plant.actual = actual
    summary.water_plant.power_used = actual * constants["power_per_l"]
    summary.water_plant.oxygen_used = actual * constants["oxygen_per_l"]
    state.resources["power"].value -= summary.water_plant.power_used
    state.resources["oxygen"].value = max(0, state.resources["oxygen"].value - summary.water_plant.oxygen_used)
    state.resources["water"].value += actual
    check_deaths(state, summary, events)
