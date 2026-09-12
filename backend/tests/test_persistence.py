from backend.domain.models import create_initial_state
from backend.persistence.db import Database
from backend.persistence.repositories import WorldHistory


def test_snapshot_survives_database_reopen(tmp_path):
    path = str(tmp_path / 'world.sqlite3')
    database = Database(path)
    history = WorldHistory(database)
    state = create_initial_state()
    history.save(state)
    database.close()
    database = Database(path)
    assert WorldHistory(database).latest() == state
    database.close()


def test_history_handles_reset_version_and_preserves_message_order():
    database = Database()
    history = WorldHistory(database)
    assert history.latest() is None
    state = create_initial_state()
    state.tick = 5
    state.version = 5
    history.save(state)
    reset = create_initial_state()
    history.save(reset)
    assert history.latest() == reset
    history.record('tick_plan', {'tick': 0})
    history.record('state_update', {'tick': 1})
    assert [row['type'] for row in history.recent()] == ['tick_plan', 'state_update']
    database.close()
