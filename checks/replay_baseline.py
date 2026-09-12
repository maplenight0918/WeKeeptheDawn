"""Guide baseline REGRESSION POLICY, exclusively for checks and fixture recording.

This rule controller is NOT the Core Agent, a runtime fallback, or an Agent tool.
It implements guide's documented test-only refill/replant/harvest/work schedule.
All inventory transitions are produced by WorldEngine. Runtime reads the tape.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.domain.config import C, CROPS, crew_consumption_per_tick, harvest_food
from backend.domain.models import TickPlan, Refill, PlotOp, WorldState, create_initial_state
from backend.engine.world_engine import WorldEngine
from backend.orchestration.plan_validator import PlanValidator


class BaselinePolicy:
    """Explicit guide regression fixture policy. Never imported by backend runtime."""
    def __init__(self, initial):
        self.crop_by_plot = {plot.id: plot.crop for plot in initial.plots}

    def plan(self, state):
        request = TickPlan(tick=state.tick, state_version=state.version,
                           rationale='MOCK regression tape: documented guide test schedule')
        baseline = crew_consumption_per_tick()
        free = []
        for crew in state.crew.values():
            # This priority is explicitly permitted ONLY in this regression policy.
            needs = [field for field in ('food_energy', 'water')
                     if getattr(crew, field) < C['crew'][field]['warning']]
            if needs:
                field = min(needs, key=lambda item: getattr(crew, item) / baseline[item])
                request.refills.append(Refill(crew_id=crew.id, kind='food' if field == 'food_energy' else 'water',
                                             amount=C['crew'][field]['refill_max']))
            else:
                free.append(crew.id)
        food_room = state.resources['food'].capacity - state.resources['food'].value - state.pending_food
        for refill in request.refills:
            if refill.kind == 'food':
                food_room += min(refill.amount, C['crew']['food_energy']['capacity'] - state.crew[refill.crew_id].food_energy)
        empties = [plot for plot in state.plots if plot.crop is None]
        mature = [plot for plot in state.plots if plot.mature and not plot.dead]
        for plot in empties + mature:
            if not free:
                break
            op = 'plant' if plot.crop is None else 'harvest'
            if op == 'harvest' and harvest_food(plot.crop) > food_room:
                continue
            crew_id = free.pop(0)
            request.plot_ops.append(PlotOp(order=len(request.plot_ops), crew_id=crew_id, plot_id=plot.id,
                                           op=op, crop=self.crop_by_plot[plot.id] if op == 'plant' else None))
            if op == 'harvest':
                food_room -= harvest_food(plot.crop)
        request.generation = {crew_id: C['generation']['max_work_per_crew'] for crew_id in free}
        request.irrigation = [plot.id for plot in state.plots if plot.crop and not plot.dead]
        request.water_production_l = len(request.irrigation) * C['irrigation']['water_l']
        request.water_production_l += sum(min(item.amount, C['crew']['water']['capacity'] - state.crew[item.crew_id].water)
                                          for item in request.refills if item.kind == 'water')
        return request


def thoughts(stage='normal'):
    return [
        {'local_id': 'observe', 'agent': 'core', 'kind': 'observe',
         'text': '這回合要核對公共庫存、人員存量與地塊狀態，讓供應和工作安排接得上。' if stage == 'normal'
                 else '玩家調低了電力。我們需要重新核對灌溉供應和可用人力。',
         'payload': {'to': 'all'}},
        {'local_id': 'risk', 'agent': 'core', 'kind': 'risk',
         'text': 'Plant，請說明作物供應風險；Human，請確認人員補充與發電是否衝突。',
         'payload': {'to': ['plant', 'human'], 'reply_to': 'observe'}},
        {'local_id': 'plant_advice', 'agent': 'plant', 'kind': 'advice',
         'text': '收到。未獲完整水電的地塊會停止生長並累計灌溉中斷，成熟作物也需要供應。請依本回合地塊清單檢查。',
         'payload': {'to': 'core', 'reply_to': 'risk'}},
        {'local_id': 'human_advice', 'agent': 'human', 'kind': 'advice',
         'text': '我來確認人力：補充和作物工作都占用整個回合，同一人不能同時發電。計畫已將這些工作分開指派。',
         'payload': {'to': 'core', 'reply_to': 'risk'}},
        {'local_id': 'plan', 'agent': 'core', 'kind': 'plan',
         'text': '兩邊的提醒收到了。確認本回合以這份 TickPlan 的人員指派與灌溉清單送驗，通過後由世界執行。',
         'payload': {'to': 'all', 'reply_to': 'human_advice', 'in_reply_to': ['plant_advice', 'human_advice']}},
        {'local_id': 'reflection', 'agent': 'core', 'kind': 'reflection',
         'text': '本回合結算已回報。實際供應、產出與人員狀態請看結果摘要，作為下一輪討論依據。',
         'payload': {'to': 'all', 'reply_to': 'plan'}},
    ]


def record_entry(state, request, stage='normal'):
    return {'tick': state.tick, 'plan': request.model_dump(mode='json'), 'thoughts': thoughts(stage)}


def replay(ticks=7200, tape_length=360):
    state = create_initial_state()
    policy = BaselinePolicy(state)
    minima = {key: resource.value for key, resource in state.resources.items()}
    personal_min = {field: min(getattr(crew, field) for crew in state.crew.values()) for field in ('food_energy', 'water')}
    tape = []
    harvested = planted = 0
    for _ in range(ticks):
        request = policy.plan(state)
        errors = PlanValidator.check(state, request)
        if errors:
            raise AssertionError(f'Invalid baseline at tick {state.tick}: {errors}')
        if len(tape) < tape_length:
            tape.append(record_entry(state, request))
        state, summary, events = WorldEngine.settle(state, request)
        if state.failed or summary.irrigation.failed:
            raise AssertionError(f'Baseline failed tick {state.tick}: {state.failure_reason}; plots {summary.irrigation.failed}')
        harvested += len(summary.harvested)
        planted += len(summary.planted)
        for key, resource in state.resources.items():
            minima[key] = min(minima[key], resource.value)
        for field in personal_min:
            personal_min[field] = min(personal_min[field], *(getattr(crew, field) for crew in state.crew.values()))
    report = {'ticks': ticks, 'alive': sum(crew.alive for crew in state.crew.values()), 'harvested': harvested,
              'planted': planted, 'resource_minima': minima, 'personal_minima': personal_min,
              'note': 'Locally measured regression; not an exact reproduction of unavailable historical scripts.'}
    return state, report, tape


def demo():
    state = create_initial_state()
    policy = BaselinePolicy(state)
    frames = [{'label': 'initial', 'state': state.model_dump(mode='json'), 'thoughts': [], 'plan': None}]
    for _ in range(2):
        request = policy.plan(state)
        state, _, _ = WorldEngine.settle(state, request)
        frames.append({'label': 'normal', 'state': state.model_dump(mode='json'), 'thoughts': thoughts(), 'plan': request.model_dump(mode='json')})
    # 300 is the user-requested demo intervention, not a world coefficient.
    state, _ = WorldEngine.edit_resources(state, {'power': 300})
    frames.append({'label': 'power_edit', 'state': state.model_dump(mode='json'), 'thoughts': [], 'plan': None})
    branch = []
    for index in range(3):
        request = policy.plan(state)
        if index < 2:
            request.irrigation = [plot.id for plot in state.plots if plot.crop in ('potato', 'wheat', 'soybean')]
        if index == 0:
            crew_id = next(iter(state.crew))
            request.refills = [Refill(crew_id=crew_id, kind='food', amount=C['crew']['food_energy']['refill_max'])]
            request.generation = {key: C['generation']['max_work_per_crew'] for key in state.crew if key != crew_id}
        errors = PlanValidator.check(state, request)
        assert not errors, errors
        branch.append(record_entry(state, request, 'power_edit'))
        state, summary, _ = WorldEngine.settle(state, request)
        assert not state.failed
        assert len(summary.irrigation.succeeded) == (12 if index < 2 else C['plots']['count'])
        frames.append({'label': 'partial' if index < 2 else 'recovered', 'state': state.model_dump(mode='json'),
                       'thoughts': thoughts('power_edit'), 'plan': request.model_dump(mode='json')})
    return branch, frames


def mock_timeline(ticks=60):
    """Recorded states for the browser demo; no frontend-side settlement."""
    state = create_initial_state()
    policy = BaselinePolicy(state)
    frames = [{'label': 'initial', 'state': state.model_dump(mode='json'), 'thoughts': [], 'plan': None}]
    for _ in range(ticks):
        request = policy.plan(state)
        errors = PlanValidator.check(state, request)
        if errors:
            raise AssertionError(f'Invalid mock timeline plan at tick {state.tick}: {errors}')
        state, _, _ = WorldEngine.settle(state, request)
        # Deliberately omit chat here. The opening and intervention demo frames
        # already carry recorded conversation; these frames keep the clock moving.
        frames.append({'label': 'normal', 'state': state.model_dump(mode='json'), 'thoughts': [], 'plan': None})
    return frames


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ticks', type=int, default=7200)
    parser.add_argument('--write-fixtures', action='store_true')
    args = parser.parse_args()
    _, report, normal = replay(args.ticks)
    branch, frames = demo()
    timeline = mock_timeline()
    if args.write_fixtures:
        destination = Path(__file__).resolve().parents[1] / 'backend' / 'fixtures'
        destination.mkdir(parents=True, exist_ok=True)
        (destination / 'plan_tape.json').write_text(json.dumps({'mock': True, 'normal': normal, 'power_edit': branch}, ensure_ascii=False), encoding='utf-8')
        failure_state, _ = WorldEngine.edit_resources(WorldState.model_validate(frames[-1]['state']), {'oxygen': 0})
        failure = {'label': 'failure', 'state': failure_state.model_dump(mode='json'), 'thoughts': [], 'plan': None}
        (destination / 'demo_states.json').write_text(json.dumps({'mock': True, 'frames': frames, 'failure': failure}, ensure_ascii=False), encoding='utf-8')
        (destination / 'mock_timeline.json').write_text(json.dumps({'mock': True, 'frames': timeline}, ensure_ascii=False), encoding='utf-8')
        (destination / 'baseline_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
