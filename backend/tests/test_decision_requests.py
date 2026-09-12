import asyncio

import httpx
import pytest

from backend.main import create_app
from backend.integration.settings import RuntimeSettings


async def awaiting(client, previous=None):
    for _ in range(100):
        data = (await client.get("/decision")).json()
        if data and data["request_id"] != previous:
            return data
        await asyncio.sleep(0.001)
    raise AssertionError("no decision request")


def submission(request, *, identity="test", generation=None):
    return {"request_id": request["request_id"], "submission_id": identity,
            "plan": {"tick": request["tick"], "state_version": request["state_version"],
                     "generation": generation or {}, "refills": [], "plot_ops": [],
                     "water_production_l": 0, "irrigation": []}}


@pytest.mark.asyncio
async def test_bound_submission_dedup_and_identity_conflict():
    app = create_app(mode="external", autostart=False)
    async with app.router.lifespan_context(app), httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        tick = asyncio.create_task(app.state.loop.tick())
        request = await awaiting(client)
        body = submission(request)
        first = await client.post("/ingest/decision-plan", json=body)
        second = await client.post("/ingest/decision-plan", json=body)
        assert first.status_code == second.status_code == 202
        assert second.json()["duplicate"]
        assert (await tick).tick == 1
        body["plan"]["water_production_l"] = 2
        assert (await client.post("/ingest/decision-plan", json=body)).status_code == 409
        assert app.state.repository.get().tick == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["pause", "resume", "speed", "resources", "reset"])
async def test_control_invalidates_old_failure_and_submission(command):
    app = create_app(mode="external", autostart=False)
    async with app.router.lifespan_context(app), httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        tick = asyncio.create_task(app.state.loop.tick())
        request = await awaiting(client)
        if command == "reset":
            await client.post("/world/reset")
        elif command == "resources":
            await client.post("/resources", json={"power": 10})
        else:
            await client.post("/control", json={"cmd": command, **({"value": 2} if command == "speed" else {})})
        assert (await client.post("/ingest/decision-failure", json={"request_id": request["request_id"]})).status_code == 409
        assert (await client.post("/ingest/decision-plan", json=submission(request))).status_code == 409
        await tick
        assert app.state.repository.get().paused_reason != "error"
        assert app.state.repository.get().tick == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("notify", [False, True])
async def test_failure_or_deadline_pauses_without_settlement(notify):
    app = create_app(mode="external", autostart=False,
                     runtime_settings=RuntimeSettings(plan_source="external", decision_timeout_seconds=0.05))
    async with app.router.lifespan_context(app), httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        events = app.state.bus.subscribe()
        tick = asyncio.create_task(app.state.loop.tick())
        request = await awaiting(client)
        if notify:
            assert (await client.post("/ingest/decision-failure", json={"request_id": request["request_id"]})).status_code == 202
        state = await asyncio.wait_for(tick, 1)
        assert state.paused_reason == "error" and state.tick == 0 and state.version == 1
        assert any(message["type"] == "world_event" and message["payload"]["type"] == "plan_failed"
                   for message in list(events._queue))


@pytest.mark.asyncio
async def test_422_not_counted_and_three_validator_rejections_settle_once():
    app = create_app(mode="external", autostart=False)
    async with app.router.lifespan_context(app), httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        tick = asyncio.create_task(app.state.loop.tick())
        request = await awaiting(client)
        bad = submission(request)
        bad["plan"]["refills"] = [{"crew_id": "c01", "kind": "food"}]
        assert (await client.post("/ingest/decision-plan", json=bad)).status_code == 422
        assert (await client.get("/decision")).json()["request_id"] == request["request_id"]
        for attempt in range(3):
            body = submission(request, identity=str(attempt), generation={"missing": 1})
            assert (await client.post("/ingest/decision-plan", json=body)).status_code == 202
            if attempt < 2:
                request = await awaiting(client, request["request_id"])
                assert request["validation_errors"]
        state = await asyncio.wait_for(tick, 1)
        assert state.tick == 1 and state.last_summary.generation.actual == 0
        assert not state.paused
