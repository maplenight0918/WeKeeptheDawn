"""Real local HTTP + WS tests. No provider calls; no external game process."""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import socket

import httpx
import pytest
import uvicorn

from backend.main import create_app
from agent_runner.core_port import CorePort
from agent_runner.fixtures import FixtureModel, FixtureSpecialist
from agent_runner.runner import AgentBridge
from core_agent.core_agent import CoreAgent, HTTPSpecialist


@asynccontextmanager
async def serve(app, *, lifespan="on"):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", lifespan=lifespan))
    task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        for _ in range(500):
            if task.done():
                task.result()
            if server.started:
                break
            await asyncio.sleep(0.01)
        else:
            raise AssertionError("server did not start")
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, 5)
        listener.close()


@pytest.mark.asyncio
async def test_real_http_ws_two_ticks_and_result_feedback():
    app = create_app(mode="external")
    port = CorePort(CoreAgent(FixtureModel(), FixtureSpecialist(), FixtureSpecialist()), mock=True)
    async with serve(app) as url, httpx.AsyncClient(base_url=url) as client:
        await client.post("/control", json={"cmd": "speed", "value": 20})
        bridge = AgentBridge(port, url)
        await asyncio.wait_for(bridge.run(max_ticks=2), 8)
        state = (await client.get("/world")).json()
        assert state["tick"] == 2
        assert state["pending_oxygen"] > 0
        assert len(port.history) == 2
        messages = (await client.get("/history", params={"limit": 500})).json()
        thoughts = [m["payload"] for m in messages if m["type"] == "agent_thought"]
        assert {t["agent"] for t in thoughts} == {"core", "plant", "human"}
        results = [t for t in thoughts if t["payload"]["source"] == "bridge_result"]
        assert len(results) == 2
        assert all(t["payload"]["status"] == "confirmed" for t in results)
        assert not any(t["kind"] == "reflection" for t in thoughts)
        assert sum(m["type"] == "tick_plan" for m in messages) == 2


@pytest.mark.asyncio
async def test_player_pause_cancels_inflight_core_and_never_auto_resumes():
    started = asyncio.Event()
    class SlowSpecialist(FixtureSpecialist):
        async def ask(self, request):
            started.set()
            await asyncio.sleep(30)
            return await super().ask(request)
    port = CorePort(CoreAgent(FixtureModel(), SlowSpecialist(), SlowSpecialist()), mock=True)
    async with serve(create_app(mode="external")) as url, httpx.AsyncClient(base_url=url) as client:
        task = asyncio.create_task(AgentBridge(port, url).run())
        try:
            await asyncio.wait_for(started.wait(), 3)
            paused = (await client.post("/control", json={"cmd": "pause"})).json()
            await asyncio.sleep(0.2)
            state = (await client.get("/world")).json()
            assert state == paused and state["paused_reason"] == "player"
            assert not port.history
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_submission_timeout_retries_same_id_without_second_settlement():
    app = create_app(mode="external")
    port = CorePort(CoreAgent(FixtureModel(), FixtureSpecialist(), FixtureSpecialist()), mock=True)
    async with serve(app) as url:
        class LostResponse(httpx.AsyncClient):
            attempts = []
            async def post(self, path, **kwargs):
                response = await super().post(path, **kwargs)
                if path == "/ingest/decision-plan":
                    self.attempts.append(kwargs["json"])
                    if len(self.attempts) == 1:
                        raise httpx.ReadTimeout("fixture: accepted response lost")
                return response
        async with LostResponse(base_url=url) as client:
            await asyncio.wait_for(AgentBridge(port, url, client=client).run(max_ticks=1), 8)
            assert len(client.attempts) == 2 and client.attempts[0] == client.attempts[1]
            assert (await client.get("/world")).json()["tick"] == 1


@pytest.mark.asyncio
async def test_bridge_three_rejections_reports_backend_empty_plan_once():
    class InvalidFixturePort(CorePort):
        calls = 0
        async def decide(self, state, errors, emit):
            self.calls += 1
            decision = await super().decide(state, errors, emit)
            decision.plan.generation = {"unknown-crew": 1}
            return decision
    port = InvalidFixturePort(CoreAgent(FixtureModel(), FixtureSpecialist(), FixtureSpecialist()), mock=True)
    async with serve(create_app(mode="external")) as url:
        await asyncio.wait_for(AgentBridge(port, url).run(max_ticks=1), 8)
        assert port.calls == 3
        assert len(port.history) == 1
        result = port.history[0]
        assert result["executed_plan"]["generation"] == {}
        assert any(event["type"] == "plan_failed" for event in result["events"])
        assert port.current_plan is None


@pytest.mark.asyncio
async def test_specialist_failure_notifies_backend_error_pause():
    class Unavailable(FixtureSpecialist):
        async def ask(self, request):
            raise ConnectionError("fixture offline")
    port = CorePort(CoreAgent(FixtureModel(), Unavailable(), FixtureSpecialist()), mock=True)
    async with serve(create_app(mode="external")) as url, httpx.AsyncClient(base_url=url) as client:
        bridge = asyncio.create_task(AgentBridge(port, url).run())
        try:
            for _ in range(100):
                state = (await client.get("/world")).json()
                if state["paused_reason"] == "error":
                    break
                await asyncio.sleep(0.02)
            else:
                raise AssertionError("external failure did not pause")
            assert state["tick"] == 0 and not port.history
        finally:
            bridge.cancel()
            await asyncio.gather(bridge, return_exceptions=True)


@pytest.mark.asyncio
async def test_actual_specialist_routes_with_explicit_plant_index_fixture(monkeypatch):
    """Plant's index startup is unavailable; exercise its real conflict route only."""
    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root / "plant_agent"))
    monkeypatch.syspath_prepend(str(root / "human_agent"))
    from src.api.main import app as plant_app
    from app.main import create_app as human_app
    from app.settings import Settings

    class NoCorpus:
        def search(self, *args, **kwargs):
            raise AssertionError("conflict fixture must not call retrieval")
    monkeypatch.setattr(plant_app.state, "store", NoCorpus(), raising=False)
    async with serve(plant_app, lifespan="off") as plant_url, serve(human_app(Settings(agent_mode="mock", retrieval_mode="bm25"))) as human_url:
        port = CorePort(CoreAgent(FixtureModel(), HTTPSpecialist(plant_url + "/discuss"),
                                 HTTPSpecialist(human_url + "/discuss")), mock=True)
        async with serve(create_app(mode="external")) as game_url:
            await asyncio.wait_for(AgentBridge(port, game_url).run(max_ticks=1), 15)
            assert len(port.history) == 1
            async with httpx.AsyncClient(base_url=game_url) as client:
                messages = (await client.get("/history", params={"limit": 500})).json()
            plant = next(m["payload"] for m in messages if m["type"] == "agent_thought" and m["payload"]["agent"] == "plant")
            assert plant["payload"]["explanation"]["conflicts"]
            assert port.rules["irrigation"]["power_per_plot"] == 5
