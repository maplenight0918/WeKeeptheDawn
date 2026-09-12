"""Player intervention -> cancellation -> fresh three-way discussion; no paid models."""
import asyncio
from copy import deepcopy

import httpx
import pytest

from agent_runner.core_port import CorePort
from agent_runner.fixtures import FixtureModel, FixtureSpecialist
from agent_runner.runner import AgentBridge
from backend.domain.config import C
from backend.domain.models import TickPlan
from backend.domain.models import create_initial_state
from backend.main import create_app
from backend.tests.test_bridge_http import serve
from core_agent.core_agent import CoreAgent


class EmergencyFixtureModel(FixtureModel):
    """Explicit test-only repair plan, not a production emergency policy."""
    def __init__(self):
        self.initial = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.fresh = asyncio.Event()
        self.release = asyncio.Event()
        self.worlds = []

    async def decide(self, context):
        self.worlds.append(deepcopy(context["world"]))
        if len(self.worlds) == 1:
            self.initial.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                self.cancelled.set()
                raise
        self.fresh.set()
        await self.release.wait()
        result = await super().decide(context)
        stage = result["plan"]["stages"][0]
        rules = context["rules"]
        stage["actions"] = [{"action_id": f"emergency-test-{crew['id']}", "crew_id": crew["id"],
            "kind": "generate", "tick_offset": 0, "repeat": False, "plot_id": None, "crop_type": None,
            "amount": rules["generation"]["max_units_per_crew_tick"]} for crew in context["world"]["crew"][:2]]
        stage["water_liters_per_tick"] = (len(stage["irrigation_order"]) * rules["irrigation"]["water_per_plot"]
                                             + rules["crew"]["refill_limit"]["drink"])
        result["summary"] = "Emergency 測試 fixture：依修改後快照提交明確發電、製水與灌溉；非真實模型救援策略。"
        return result


class RecordingSpecialist(FixtureSpecialist):
    def __init__(self):
        self.worlds = []

    async def ask(self, request):
        self.worlds.append(deepcopy(request.content["world"]))
        return await super().ask(request)


@pytest.mark.asyncio
@pytest.mark.parametrize("key,value", [("power", 0), ("water", 0), ("food", 0),
                                         ("oxygen", C["resources"]["oxygen"]["warning"] / 2)])
async def test_resource_emergency_invalidates_old_plan_and_replans(key, value):
    model = EmergencyFixtureModel()
    plant, human = RecordingSpecialist(), RecordingSpecialist()
    port = CorePort(CoreAgent(model, plant, human), mock=True)
    async with serve(create_app(mode="external")) as url, httpx.AsyncClient(base_url=url) as client:
        task = asyncio.create_task(AgentBridge(port, url).run(max_ticks=1))
        try:
            await asyncio.wait_for(model.initial.wait(), 5)
            original = (await client.get("/world")).json()
            old_request = (await client.get("/decision")).json()
            changed = (await client.post("/resources", json={key: value})).json()
            assert not changed["failed"] and changed["tick"] == original["tick"] == 0
            assert changed["resources"][key]["value"] == value < changed["resources"][key]["warning"]
            assert changed["version"] == original["version"] + 1
            await asyncio.wait_for(model.cancelled.wait(), 5)
            await asyncio.wait_for(model.fresh.wait(), 5)
            assert (await client.get("/world")).json() == changed  # No ticking while planning.
            assert (await client.post("/ingest/decision-plan", json={
                "request_id": old_request["request_id"], "submission_id": "stale-emergency-test",
                "plan": TickPlan(tick=0, state_version=original["version"]).model_dump()})).status_code == 409
            assert (await client.post("/ingest/decision-failure", json={
                "request_id": old_request["request_id"]})).status_code == 409
            for worlds in (model.worlds, plant.worlds, human.worlds):
                assert worlds[-1]["world_version"] == changed["version"]
                assert worlds[-1]["resources"][key] == value
            model.release.set()
            await asyncio.wait_for(task, 8)
            result = (await client.get("/world")).json()
            assert result["tick"] == 1 and not result["failed"]
            assert result["last_summary"]["generation"]["power_out"] > 0
            assert not result["last_summary"]["irrigation"]["failed"]
            assert len(port.history) == 1
            assert port.history[0]["state_version"] == changed["version"]
            history = (await client.get("/history", params={"limit": 1000})).json()
            assert sum(e["type"] == "tick_plan" for e in history) == 1
            assert any(e["type"] == "world_event" and e["payload"]["type"] == "player_edit" for e in history)
            assert not any(e["type"] == "agent_thought" and e["payload"]["kind"] == "reflection" for e in history)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_oxygen_zero_kills_immediately_and_never_starts_new_decision():
    model = EmergencyFixtureModel()
    port = CorePort(CoreAgent(model, RecordingSpecialist(), RecordingSpecialist()), mock=True)
    async with serve(create_app(mode="external")) as url, httpx.AsyncClient(base_url=url) as client:
        task = asyncio.create_task(AgentBridge(port, url).run())
        try:
            await asyncio.wait_for(model.initial.wait(), 5)
            failed = (await client.post("/resources", json={"oxygen": 0})).json()
            assert failed["failed"] and failed["tick"] == 0
            assert all(not crew["alive"] for crew in failed["crew"].values())
            await asyncio.wait_for(model.cancelled.wait(), 5)
            await asyncio.sleep(0.2)
            assert len(model.worlds) == 1 and not port.history
            assert (await client.get("/decision")).json() is None
            assert (await client.get("/world")).json() == failed
            history = (await client.get("/history", params={"limit": 1000})).json()
            assert not any(e["type"] == "tick_plan" for e in history)
            assert any(e["type"] == "mission_failed" for e in history)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_resource_emergency_while_paused_never_resumes_player_world():
    model = EmergencyFixtureModel()
    port = CorePort(CoreAgent(model, RecordingSpecialist(), RecordingSpecialist()), mock=True)
    async with serve(create_app(mode="external")) as url, httpx.AsyncClient(base_url=url) as client:
        await client.post("/control", json={"cmd": "pause"})
        task = asyncio.create_task(AgentBridge(port, url).run())
        try:
            edited = (await client.post("/resources", json={"power": 0})).json()
            await asyncio.sleep(0.25)
            assert edited["paused_reason"] == "player" and edited["tick"] == 0
            assert not edited["failed"]
            assert (await client.get("/world")).json() == edited
            assert (await client.get("/decision")).json() is None
            assert not model.worlds and not port.history
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_pending_oxygen_cannot_rescue_player_oxygen_zero(monkeypatch):
    initial = create_initial_state()
    initial.pending_oxygen = 304
    initial.pending_food = 20
    monkeypatch.setattr("backend.main.create_initial_state", lambda: initial.model_copy(deep=True))
    async with serve(create_app(mode="external")) as url, httpx.AsyncClient(base_url=url) as client:
        failed = (await client.post("/resources", json={"oxygen": 0})).json()
        assert failed["failed"] and failed["tick"] == 0
        assert failed["pending_oxygen"] == 0
        assert failed["pending_food"] == initial.pending_food
        assert all(not c["alive"] for c in failed["crew"].values())
