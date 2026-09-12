"""One test for each of spec §11's 23 acceptance rows."""
import pytest
from backend.domain.config import C, CROPS, crew_consumption_per_tick
from backend.domain.models import create_initial_state, TickPlan, PlotOp, Refill
from backend.engine.world_engine import WorldEngine


def run(s, **kw):
    return WorldEngine.settle(s, TickPlan(tick=s.tick, **kw))


def ready(s, crop):
    p = next(p for p in s.plots if p.crop == crop)
    p.mature = True
    p.progress_ticks = CROPS[crop]['maturity_ticks']
    return p


def harvest(s, p):
    return run(s, plot_ops=[PlotOp(order=0, crew_id=next(iter(s.crew)), plot_id=p.id, op='harvest')])


def test_guide_2_2_row01_potato():
    s = create_initial_state()
    out, summary, _ = harvest(s, ready(s, 'potato'))
    assert out.pending_food == summary.harvested[0].food == 8775
    assert out.resources['food'].value == s.resources['food'].value


def test_guide_2_2_row02_lettuce():
    s = create_initial_state()
    out, summary, _ = harvest(s, ready(s, 'lettuce'))
    assert out.pending_food == summary.harvested[0].food == 585


def test_guide_2_5_row03_water_174():
    s = create_initial_state()
    out, summary, _ = run(s, water_production_l=174)
    assert out.resources['water'].value - s.resources['water'].value == 174
    assert summary.water_plant.power_used == 348
    assert summary.water_plant.oxygen_used == pytest.approx(34.8)


def test_guide_2_5_row04_water_400():
    assert run(create_initial_state(), water_production_l=400)[1].water_plant.actual == 250


def test_guide_2_4_row05_full_generation():
    s = create_initial_state()
    out, summary, _ = run(s, generation={key: 1 for key in s.crew})
    assert summary.generation.power_out == 1000
    assert summary.generation.oxygen_used == 100
    for key, crew in out.crew.items():
        assert s.crew[key].food_energy - crew.food_energy - crew_consumption_per_tick()['food_energy'] == 100
    assert out.resources['food'].value == s.resources['food'].value


def test_guide_2_3_2_4_row06_full_generation_baseline():
    s = create_initial_state()
    out, _, _ = run(s, generation={key: 1 for key in s.crew})
    assert sum(s.crew[key].food_energy - crew.food_energy for key, crew in out.crew.items()) == 909
    assert s.resources['oxygen'].value - out.resources['oxygen'].value == pytest.approx(4 * (0.895 * 1000 / 24 + 25))
    assert sum(s.crew[key].water - crew.water for key, crew in out.crew.items()) == pytest.approx(4 * 3.217 / 24)


def test_guide_2_4_row07_energy_cap_and_death():
    for remainder, expected in ((150, 1), (80, .8)):
        s = create_initial_state()
        key = next(iter(s.crew))
        s.crew[key].food_energy = remainder + crew_consumption_per_tick()['food_energy']
        out, summary, _ = run(s, generation={key: 1})
        assert summary.generation.actual == expected
        assert out.failed == (remainder == 80)


def test_guide_2_1_row08_twenty_irrigated():
    s = create_initial_state()
    summary = run(s, irrigation=[p.id for p in s.plots])[1]
    assert summary.irrigation.water_used == pytest.approx(174)
    assert summary.irrigation.power_used == 100
    assert len(summary.irrigation.succeeded) == 20


def test_guide_2_1_row09_twelve_irrigated():
    s = create_initial_state()
    out, summary, _ = run(s, irrigation=[p.id for p in s.plots[:12]])
    assert len(summary.irrigation.failed) == 8
    assert all(p.consecutive_unirrigated_ticks == 1 for p in out.plots[12:])
    assert summary.oxygen_produced == sum(CROPS[p.crop]['oxygen_per_tick'] for p in s.plots[:12])


def test_guide_2_1_row10_third_failure_before_harvest():
    s = create_initial_state()
    p = ready(s, 'potato')
    p.consecutive_unirrigated_ticks = 2
    out, summary, _ = harvest(s, p)
    assert next(q for q in out.plots if q.id == p.id).dead
    assert not summary.harvested
    assert out.pending_food == 0


def test_guide_2_1_row11_recovery():
    s = create_initial_state()
    s.plots[0].progress_ticks = 5
    s.plots[0].consecutive_unirrigated_ticks = 2
    out, _, _ = run(s, irrigation=[s.plots[0].id])
    assert out.plots[0].progress_ticks == 6
    assert out.plots[0].consecutive_unirrigated_ticks == 0


def test_guide_2_1_row12_corrected_overflow_premise():
    s = create_initial_state()
    s.resources['oxygen'].value = s.resources['oxygen'].capacity
    out, summary, events = run(s, irrigation=[p.id for p in s.plots])
    assert out.resources['oxygen'].value + out.pending_oxygen == s.resources['oxygen'].capacity
    assert summary.oxygen_overflow == pytest.approx(304 - crew_consumption_per_tick()['oxygen'] * len(s.crew))
    assert any(e.type == 'oxygen_overflow' for e in events)


def test_guide_2_6_row13_pending_oxygen():
    s = create_initial_state()
    out, summary, _ = run(s, irrigation=[s.plots[0].id])
    assert out.pending_oxygen == summary.oxygen_produced
    expected = out.resources['oxygen'].value + out.pending_oxygen - crew_consumption_per_tick()['oxygen'] * len(s.crew)
    following, _, _ = run(out)
    assert following.resources['oxygen'].value == pytest.approx(expected)
    assert following.pending_oxygen == 0


def test_guide_2_6_row14_generation_to_water():
    s = create_initial_state()
    s.resources['power'].value = 0
    assert run(s, generation={next(iter(s.crew)): 1}, water_production_l=100)[1].water_plant.actual == 100


def test_guide_2_2_row15_harvest_capacity():
    s = create_initial_state()
    s.resources['food'].value = s.resources['food'].capacity - 500
    p = ready(s, 'potato')
    out, summary, events = harvest(s, p)
    assert not summary.harvested
    assert next(q for q in out.plots if q.id == p.id).mature
    assert any(e.type == 'harvest_blocked_capacity' for e in events)


def test_guide_2_3_row16_refill_partial_occupancy():
    s = create_initial_state()
    key = next(iter(s.crew))
    s.resources['food'].value = 300
    s.crew[key].food_energy = C['crew']['food_energy']['capacity'] - 800
    out, summary, _ = run(s, refills=[Refill(crew_id=key, kind='food', amount=1000)])
    assert summary.refills[0].amount == 300
    assert out.crew[key].current_task == 'eating'
    assert out.crew[key].work_this_tick == 0
    assert out.resources['food'].value == 0


def test_guide_2_3_row17_personal_water_death():
    s = create_initial_state()
    key = next(iter(s.crew))
    s.crew[key].water = .1
    out, summary, events = run(s, water_production_l=174, irrigation=[p.id for p in s.plots])
    assert out.failed and not out.crew[key].alive
    assert summary.water_plant.actual == 0
    assert not summary.irrigation.attempted
    assert any(e.type == 'mission_failed' for e in events)


def test_guide_2_3_row18_exact_oxygen_zero():
    s = create_initial_state()
    s.resources['oxygen'].value = crew_consumption_per_tick()['oxygen'] * len(s.crew)
    out, summary, _ = run(s, irrigation=[p.id for p in s.plots])
    assert out.failed and all(not c.alive for c in out.crew.values())
    assert out.resources['oxygen'].value == 0
    assert summary.oxygen_produced == 0


def test_guide_2_3_row19_player_oxygen_zero():
    from backend.orchestration.player import edit_resources
    s = create_initial_state()
    out, events = edit_resources(s, {'oxygen': 0})
    assert out.failed and all(not c.alive for c in out.crew.values())
    assert out.tick == s.tick
    assert any(e.type == 'mission_failed' for e in events)


def test_guide_1_3_row20_pause_five_ticks():
    s = create_initial_state()
    s.paused = True
    before = s.model_dump()
    for _ in range(5):
        s, _, events = run(s)
        assert not events
    assert s.model_dump() == before


def test_guide_3_2_row21_harvest_plant_same_crew():
    from backend.orchestration.plan_validator import PlanValidator
    s = create_initial_state()
    p = ready(s, 'potato')
    key = next(iter(s.crew))
    request = TickPlan(tick=s.tick, plot_ops=[PlotOp(order=0, crew_id=key, plot_id=p.id, op='harvest'), PlotOp(order=1, crew_id=key, plot_id=p.id, op='plant', crop='potato')])
    assert 'SAME_CREW_HARVEST_AND_PLANT' in {e.code for e in PlanValidator.check(s, request)}


def test_guide_3_2_row22_refill_generation_double_booking():
    from backend.orchestration.plan_validator import PlanValidator
    s = create_initial_state()
    key = next(iter(s.crew))
    request = TickPlan(tick=s.tick, generation={key: .5}, refills=[Refill(crew_id=key, kind='food', amount=C['crew']['food_energy']['refill_max'])])
    assert 'CREW_DOUBLE_BOOKED' in {e.code for e in PlanValidator.check(s, request)}


def test_guide_3_3_row23_prompt_policy_rejected(tmp_path):
    from backend.agents.policy import assert_prompts_no_policy
    path = tmp_path / 'plant.md'
    path.write_text('總是先灌溉馬鈴薯；優先', encoding='utf-8')
    with pytest.raises(ValueError):
        assert_prompts_no_policy([path])
