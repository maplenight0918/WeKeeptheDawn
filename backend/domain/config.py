"""Load the sole world parameter sources; derived quantities remain formulas."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SHARED_DIR = Path(__file__).resolve().parents[2] / "shared"


def unwrap(value: Any) -> Any:
    if isinstance(value, dict):
        if "value" in value and "source" in value:
            return value["value"]
        return {key: unwrap(item) for key, item in value.items()}
    if isinstance(value, list):
        return [unwrap(item) for item in value]
    return value


def load_parameters(filename: str) -> dict[str, Any]:
    return json.loads((SHARED_DIR / filename).read_text(encoding="utf-8"))


RAW_CONSTANTS = load_parameters("world_constants.json")
RAW_CROPS = load_parameters("crops.json")
C = unwrap(RAW_CONSTANTS)
CROPS = unwrap(RAW_CROPS)


def crop_yield_g(crop_key: str) -> float:
    crop = CROPS[crop_key]
    return (crop["yield_g_m2_day"] * C["plots"]["area_m2"]
            * crop["maturity_ticks"] * C["time"]["crop_days_per_growth_tick"]
            * C["harvest"]["convertible_fraction"])


def harvest_food(crop_key: str) -> float:
    return crop_yield_g(crop_key) * CROPS[crop_key]["kcal_per_g"]


def crew_consumption_per_tick() -> dict[str, float]:
    daily = C["crew"]["daily_consumption"]
    conversion = C["crew"]["conversion"]
    tick_fraction = C["time"]["simulation_hours_per_tick"] / C["time"]["hours_per_day"]
    return {
        "food_energy": daily["food_energy"] * conversion["food_energy"] * tick_fraction,
        "water": daily["water"] * conversion["water"] * tick_fraction,
        "oxygen": daily["oxygen_kg"] * conversion["oxygen_ou_per_kg"] * tick_fraction,
    }
