"""Versioned Core input. Share this document with specialists and the world owner."""
from copy import deepcopy

# Plant equipment model: full precision, hourly electricity independent of crop acceleration.
KWH_PER_EU = 3.9745
PLANT_POWER_KW_PER_PLOT = (250 * 5 / 2.3 * 1.45 + 8 * 5) / 1000
PLANT_POWER_EU_PER_TICK = PLANT_POWER_KW_PER_PLOT / KWH_PER_EU

_RULES = {
    'rules_version': 'greenhouse-2026-09-12-v2',
    'tick_hours': 1,
    'electricity_reference': {
        'kWh_per_EU': KWH_PER_EU,
        'plot_area_m2': 5,
        'power_kW_per_plot': PLANT_POWER_KW_PER_PLOT,
        'formula': '(250 * 5 / 2.3 * 1.45 + 8 * 5) / 1000',
        'time_basis': 'equipment kW * tick_hours / kWh_per_EU; no crop growth acceleration',
        'scope': 'growing/mature plots; LED, air conditioning and pump conservative 24h model; no additional charge',
    },
    'environment': {'carbon_dioxide': {'value': 500, 'unit': 'ppm', 'adjustable': False}},
    'resources': {'food': {'unit': 'game_kcal', 'capacity': 200000, 'warning': 12000},
                  'water': {'unit': 'L', 'capacity': 4000, 'warning': 400},
                  'oxygen': {'unit': 'OU', 'capacity': 15000, 'warning': 600},
                  'power': {'unit': 'EU', 'capacity': 10000, 'warning': 1000}},
    'crew': {'daily_reference': {'kcal': 3054, 'oxygen_kg': .895, 'water_L': 3.217},
             'per_tick': {'food_energy': 3054/24, 'oxygen': 895/24, 'water': 3.217/24},
             'capacity': {'food_energy': 3000, 'water': 2},
             'warning': {'food_energy': 700, 'water': .4},
             'refill_limit': {'eat': 1000, 'drink': .5}, 'refill_ratio': 1,
             'death': 'personal energy or water <= 0; any crew death ends mission'},
    'generation': {'food_energy': 100, 'oxygen': 25, 'power': 250,
                   'max_units_per_crew_tick': 1, 'stations': 4},
    'water_production': {'power_per_L': 2, 'oxygen_per_L': .2, 'max_L_per_tick': 250},
    'irrigation': {'water_per_plot': 8.7, 'power_per_plot': PLANT_POWER_EU_PER_TICK,
                   'atomic_inputs': True, 'misses_until_death': 3,
                   'priority': 'Core supplied order; omitted living plots receive nothing',
                   'failure': 'no input deducted, no growth or oxygen; success resets misses',
                   'dead': 'no consumption or yield; clear before planting'},
    'crops': dict(zip(('lettuce', 'potato', 'tomato', 'wheat', 'soybean'), [
        {'maturity_ticks': t, 'harvest_game_kcal': f, 'oxygen_per_tick': o}
        for t, f, o in [(30,585,16),(90,8775,16),(90,1755,22),
                        (90,13162.5,10),(90,12162.15,12)]])),
    'tasks': {'occupancy': 'eat, drink, generate, plant, harvest, clear: one crew per tick',
              'controls_and_movement': 'visual only, no occupancy',
              'crop_actions': 'at tick end, ordered; no premature harvest; full storage blocks harvest',
              'plant': 'empty plot only; no seed cost; starts growing next tick'},
    'oxygen_death': 'public oxygen <= 0 immediately kills all crew, even before plants produce oxygen',
    'tick_order': ['ordered refill', 'personal metabolism', 'public breathing',
                   'generation', 'water production', 'ordered irrigation', 'ordered crop actions'],
    'planning': 'world paused while planning; validate state version before apply; no simulator',
    'completion': 'no stable/success threshold; continue until death',
}


def get_rules():
    return deepcopy(_RULES)
