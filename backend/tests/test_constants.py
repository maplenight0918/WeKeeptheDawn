"""Guide acceptance expectations are test oracles, never runtime parameters."""
import pytest

from backend.domain.config import (C, CROPS, RAW_CONSTANTS, RAW_CROPS,
                                   crop_yield_g, crew_consumption_per_tick, harvest_food)
from checks.verify_constants import numeric_leaves


@pytest.mark.parametrize("crop,grams,food", [
    ("lettuce", 2925, 585),
    ("potato", 7312.5, 8775),
    ("tomato", 5850, 1755),
    ("wheat", 4387.5, 13162.5),
    ("soybean", 3118.5, 12162.15),
])
def test_guide_2_2_yields_are_calculated(crop, grams, food):
    assert crop_yield_g(crop) == pytest.approx(grams)
    assert harvest_food(crop) == pytest.approx(food)
    assert "harvest_food" not in CROPS[crop]


def test_guide_2_2_potato_derivation_uses_source(monkeypatch):
    previous = harvest_food("potato")
    monkeypatch.setitem(CROPS["potato"], "yield_g_m2_day", CROPS["potato"]["yield_g_m2_day"] * 2)
    assert harvest_food("potato") == previous * 2


def test_guide_2_3_daily_consumption_is_unrounded():
    actual = crew_consumption_per_tick()
    assert actual["food_energy"] == 3054 / 24
    assert actual["water"] == pytest.approx(3.217 / 24, abs=1e-15)
    assert actual["oxygen"] == pytest.approx(0.895 * 1000 / 24, abs=1e-13)
    assert actual["water"] != 0.134042
    assert actual["oxygen"] != 37.291667


def test_guide_1_2_initial_plot_layout_and_density():
    assert C["plots"]["count"] == len(CROPS) * C["plots"]["initial_per_crop"]
    assert C["plots"]["area_m2"] * C["plots"]["plants_per_m2"] == 135


def test_guide_all_numeric_constants_have_sources():
    assert list(numeric_leaves(RAW_CONSTANTS))
    assert list(numeric_leaves(RAW_CROPS))


def test_guide_2_4_full_generation_plus_baseline():
    baseline = crew_consumption_per_tick()
    crew_count = C["crew"]["count"]
    generation = C["generation"]
    assert crew_count * (baseline["food_energy"] + generation["food_energy_per_work"]) == 909
    assert crew_count * generation["power_per_work"] == 1000
    assert crew_count * (baseline["oxygen"] + generation["oxygen_per_work"]) == pytest.approx(249.16666666666666)


def test_guide_2_1_initial_oxygen_does_not_overflow():
    produced = sum(crop["oxygen_per_tick"] for crop in CROPS.values()) * C["plots"]["initial_per_crop"]
    assert produced == 304
    assert C["resources"]["oxygen"]["initial"] + produced < C["resources"]["oxygen"]["capacity"]
