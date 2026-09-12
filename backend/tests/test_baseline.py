from checks.replay_baseline import replay, demo
from backend.domain.config import C


def test_guide_baseline_7200_ticks_with_crew_task_occupancy():
    state, report, tape = replay(7200, tape_length=1)
    assert state.tick == 7200
    assert report['alive'] == C['crew']['count']
    assert report['harvested'] > 0 and report['planted'] > 0
    assert all(value > 0 for value in report['personal_minima'].values())
    assert tape[0]['plan']['tick'] == 0


def test_demo_branch_is_recorded_from_engine_and_recovers():
    plans, frames = demo()
    assert [len(entry['plan']['irrigation']) for entry in plans] == [12, 12, C['plots']['count']]
    partial = [frame for frame in frames if frame['label'] == 'partial']
    assert sum(plot['consecutive_unirrigated_ticks'] == 1 for plot in partial[0]['state']['plots']) == 8
    assert sum(plot['consecutive_unirrigated_ticks'] == 2 for plot in partial[1]['state']['plots']) == 8
    assert all(plot['consecutive_unirrigated_ticks'] == 0 for plot in frames[-1]['state']['plots'])
