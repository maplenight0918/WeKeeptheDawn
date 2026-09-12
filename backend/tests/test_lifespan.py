from __future__ import annotations

import asyncio
import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app


def test_manual_app_does_not_start_ticks_and_closes_database() -> None:
    app = create_app(autostart=False)
    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200
        assert app.state.repository.get().tick == 0
        assert app.state.runner is None
        assert client.portal.call(app.state.history.latest).tick == 0
        connection = app.state.history.database.connection
        # Check closure on the SQLite owning thread before its portal exits.
        original_close = app.state.history.database.close
        closed = []

        def checked_close():
            original_close()
            with pytest.raises(sqlite3.ProgrammingError, match="closed"):
                connection.execute("SELECT 1")
            closed.append(True)

        app.state.history.database.close = checked_close
    assert closed == [True]


def test_external_autostart_waits_without_advancing_and_cleans_up() -> None:
    app = create_app(mode="external")
    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200
        assert app.state.repository.get().tick == 0
        assert app.state.runner is not None
        runner = app.state.runner
    assert runner.done()
    assert not app.state.loop.planning


def test_explicit_resume_restores_snapshot_and_default_starts_fresh(tmp_path, monkeypatch) -> None:
    path = str(tmp_path / "world.sqlite3")
    monkeypatch.delenv("RESUME_WORLD", raising=False)
    initial = create_app(db_path=path, autostart=False)
    with TestClient(initial) as client:
        client.portal.call(initial.state.loop.control, "pause")
        version = initial.state.repository.get().version
    monkeypatch.setenv("RESUME_WORLD", "true")
    restored = create_app(db_path=path, autostart=False)
    with TestClient(restored):
        assert restored.state.repository.get().paused
        assert restored.state.repository.get().version == version
    monkeypatch.delenv("RESUME_WORLD")
    fresh = create_app(db_path=path, autostart=False)
    with TestClient(fresh):
        assert not fresh.state.repository.get().paused
        assert fresh.state.repository.get().version == 0


def test_start_loop_is_idempotent_and_can_restart_a_completed_runner() -> None:
    app = create_app(mode="external")
    with TestClient(app) as client:
        original = app.state.runner
        client.portal.call(app.state.start_loop)
        assert app.state.runner is original
        client.portal.call(app.state.loop.stop)
        assert original.done()
        client.portal.call(app.state.start_loop)
        assert app.state.runner is not original
        assert not app.state.runner.done()


def test_cors_allows_local_frontend() -> None:
    with TestClient(create_app(autostart=False)) as client:
        response = client.options("/resources", headers={
            "Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        })
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_invalid_plan_source_mode_rejected() -> None:
    with pytest.raises(ValueError, match="PLAN_SOURCE"):
        create_app(mode="openai")
