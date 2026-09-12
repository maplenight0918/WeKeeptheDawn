from backend.domain.config import C


def irrigate(state, plot):
    water = state.resources["water"]
    power = state.resources["power"]
    need = C["irrigation"]
    if water.value < need["water_l"] or power.value < need["power_eu"]:
        return False
    water.value -= need["water_l"]
    power.value -= need["power_eu"]
    return True
