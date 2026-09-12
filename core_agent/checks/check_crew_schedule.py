"""Development check; no agent-facing prediction API.
Baseline irrigation, immediate harvest/replant, and no crew cost for plant work.
Crew eat/drink on warning, prioritizing the smaller remaining survival margin.
"""
from decimal import Decimal as D
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core_agent.rules import get_rules
PLOT_POWER = D(str(get_rules()["irrigation"]["power_per_plot"]))

parser = argparse.ArgumentParser()
parser.add_argument("--power-per-work", type=D, default=D(250))
parser.add_argument("--ticks", type=int, default=7200)
args = parser.parse_args()
POWER_PER_WORK = args.power_per_work
assert POWER_PER_WORK > 0 and args.ticks > 0

BASE_FOOD = D(3054) / 24
BASE_WATER = D('3.217') / 24
BASE_OXYGEN = D('.895') * 1000 / 24
state = dict(food=D(120000), water=D(3000), oxygen=D(8000), power=D(6000))
caps = dict(food=D(200000), water=D(4000), oxygen=D(15000), power=D(10000))
crew = [dict(food=D(2400), water=D('1.5')) for _ in range(4)]
crops = [(30,D(585),16),(90,D(8775),16),(90,D(1755),22),
         (90,D('13162.5'),10),(90,D('12162.15'),12)]
plots = [dict(age=0,crop=c) for c in crops for _ in range(4)]
counts = dict(eat=0,drink=0,work=0)
success = f"completed {args.ticks} ticks"
result = success
minimum_resources = dict(state)
minimum_crew = dict(food=D(2400), water=D("1.5"))

def record_minimums():
    for key in state:
        minimum_resources[key] = min(minimum_resources[key], state[key])
    for person in crew:
        for key in minimum_crew:
            minimum_crew[key] = min(minimum_crew[key], person[key])
for tick in range(1,args.ticks+1):
    workers = []
    drinking = D(0)
    for person in crew:
        low_food = person['food'] < 700
        low_water = person['water'] < D('.4')
        if low_food and (not low_water or person['food']/(BASE_FOOD+100) <= person['water']/BASE_WATER):
            amount = min(D(1000), D(3000)-person['food'], state['food'])
            person['food'] += amount; state['food'] -= amount
            counts['eat'] += 1
        elif low_water:
            amount = min(D('.5'), D(2)-person['water'], state['water'])
            person['water'] += amount; state['water'] -= amount
            drinking += amount; counts['drink'] += 1
        else:
            workers.append(person)
        person['food'] -= BASE_FOOD
        person['water'] -= BASE_WATER
        assert person['food'] > 0 and person['water'] > 0, (tick, 'crew died')
    record_minimums()
    if state['oxygen'] < BASE_OXYGEN*4:
        result=f'tick {tick}: baseline oxygen unavailable'; break
    state['oxygen'] -= BASE_OXYGEN*4
    total = min(D(len(workers)), state['oxygen']/25, (caps['power']-state['power'])/POWER_PER_WORK)
    if workers:
        for person in workers:
            person['food'] -= 100*total/len(workers)
            assert person['food'] > 0, (tick, 'work depleted energy')
    counts['work'] += float(total)
    state['oxygen'] -= total*25; state['power'] += total*POWER_PER_WORK
    record_minimums()
    requested = D(174)+drinking
    actual = min(requested,D(250),state['power']/2,state['oxygen']/D('.2'),caps['water']-state['water'])
    state['power'] -= actual*2; state['oxygen'] -= actual*D('.2'); state['water'] += actual
    for plot in plots:
        if state['water'] < D('8.7') or state['power'] < PLOT_POWER:
            result=f'tick {tick}: insufficient resources for all plots'; break
        state['water'] -= D('8.7'); state['power'] -= PLOT_POWER
        state['oxygen'] = min(caps['oxygen'],state['oxygen']+plot['crop'][2])
        plot['age'] = min(plot['age']+1,plot['crop'][0])
        record_minimums()
    if result != success: break
    for plot in plots:
        if plot['age']==plot['crop'][0] and state['food']+plot['crop'][1]<=caps['food']:
            state['food']+=plot['crop'][1]; plot['age']=0
    assert all(D(0)<=v<=caps[k] for k,v in state.items())
# Optimistic long-run bound, even with perfect scheduling and full refill portions:
# w + (4*BASE_FOOD+100*w)/1000 + 4*BASE_WATER/.5 <= 4
max_work=(4-4*BASE_FOOD/1000-4*BASE_WATER/D('.5'))/D('1.1')
power_need=20*PLOT_POWER+2*(174+4*BASE_WATER)
print(result)
print('counts:',counts)
print('remaining:',{k:round(float(v),4) for k,v in state.items()})
print('optimistic long-run work units/tick:',float(max_work))
print('power output bound EU/tick:',float(max_work*POWER_PER_WORK))
print('normal power need EU/tick:',float(power_need))
print('long-run maximum margin EU/tick:',float(max_work*POWER_PER_WORK-power_need))
print('minimum resources:',{k:round(float(v),6) for k,v in minimum_resources.items()})
print('minimum crew:',{k:round(float(v),6) for k,v in minimum_crew.items()})
print('PASS' if result == success else 'FAIL')
raise SystemExit(0 if result == success else 1)
