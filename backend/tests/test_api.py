"""API boundaries and per-client WebSocket lifecycle, using no LLM."""
from fastapi.testclient import TestClient
import pytest

from backend.domain.config import C
from backend.main import create_app


@pytest.fixture
def client():
    app = create_app(mode="external", autostart=False)
    with TestClient(app) as client:
        yield client


def test_health_and_snapshot(client):
    health = client.get("/healthz")
    assert health.status_code == 200
    assert health.json() == {"status": "ok", "mode": "external", "planning": False}
    assert client.get("/world").json()["tick"] == 0


def test_multi_client_failure_first_and_reset(client):
    with client.websocket_connect("/ws") as a, client.websocket_connect("/ws") as b:
        assert a.receive_json()["type"] == b.receive_json()["type"] == "state_update"
        response = client.post("/resources", json={"oxygen": 0})
        assert response.status_code == 200
        assert response.json()["failed"]
        for socket in (a, b):
            first = socket.receive_json()
            assert first["type"] == "mission_failed"
            assert first["payload"]["reason"] == "oxygen"
        reset = client.post("/world/reset")
        assert reset.status_code == 200
        assert not reset.json()["failed"]
        assert all(crew["alive"] for crew in reset.json()["crew"].values())
    assert client.app.state.bus.subscriber_count == 0


@pytest.mark.parametrize("body", [{"water": True}, {"power": "bad"}, {"oxygen": "Infinity"}, {"unknown": 0}])
def test_invalid_resource_edits_leave_world_unchanged(client, body):
    before = client.get("/world").json()
    assert client.post("/resources", json=body).status_code == 422
    assert client.get("/world").json() == before


def test_ws_error_preserves_connection_and_state(client):
    before = client.get("/world").json()
    with client.websocket_connect("/ws") as socket:
        socket.receive_json()
        for bad in ["not json", '{"type":"edit_resources","payload":{"power":true}}',
                    '{"type":"edit_resources","payload":{"oxygen":NaN}}',
                    '{"type":"edit_resources","payload":{"oxygen":Infinity}}',
                    '{"type":"unknown","payload":{}}']:
            socket.send_text(bad)
            assert socket.receive_json()["type"] == "error"
            assert client.get("/world").json() == before
        socket.send_json({"type": "control", "payload": {"cmd": "pause"}})
        assert socket.receive_json()["payload"]["paused"]
    assert client.app.state.bus.subscriber_count == 0


def test_ws_resource_edit_uses_immediate_death_path(client):
    with client.websocket_connect("/ws") as socket:
        socket.receive_json()
        socket.send_json({"type": "edit_resources", "payload": {"oxygen": 0}})
        assert socket.receive_json()["type"] == "mission_failed"
        assert client.get("/world").json()["failed"]


def test_rest_plan_submission_is_queued_then_validated_and_executed(client):
    before = client.get("/world").json()
    with client.websocket_connect("/ws") as socket:
        socket.receive_json()
        accepted = client.post("/ingest/plan", json={"tick": before["tick"], "state_version": before["version"]})
        assert accepted.status_code == 202
        assert accepted.json()["validated"] is False
        assert client.get("/world").json() == before
        client.portal.call(client.app.state.loop.tick)
        assert socket.receive_json()["type"] == "tick_plan"
        assert client.get("/world").json()["tick"] == before["tick"] + 1


def test_thought_and_external_event_cannot_write_resources(client):
    before = client.get("/world").json()
    thought = {"id": "chat-test", "ts": 0, "tick": 0, "agent": "plant", "kind": "advice",
               "text": "展示訊息", "payload": {"resources": {"oxygen": 0}, "conversation_id": "round-test"}}
    with client.websocket_connect("/ws") as socket:
        socket.receive_json()
        assert client.post("/ingest/thought", json=thought).status_code == 202
        assert socket.receive_json() == {"type": "agent_thought", "payload": thought}
        assert client.post("/ingest/event", json={"id": "external-event", "tick": 0, "type": "player_edit",
                                                "detail": {"resources": {"oxygen": 0}}}).status_code == 202
        event = socket.receive_json()
        assert event["type"] == "world_event"
        assert event["payload"]["detail"]["source"] == "external"
        assert client.get("/world").json() == before
    assert client.post("/ingest/thought", json={**thought, "resources": {"oxygen": 0}}).status_code == 422


@pytest.mark.parametrize("kind", ["crew", "plot"])
def test_ingest_rejects_arbitrary_state_patch(client, kind):
    before = client.get("/world").json()
    assert client.post(f"/ingest/{kind}", json={"resources": {"oxygen": 0}}).status_code == 409
    assert client.get("/world").json() == before


def test_ingest_resource_uses_same_clamp_and_death_service(client):
    response = client.post("/ingest/resource", json={"power": C["resources"]["power"]["capacity"] * 2})
    assert response.status_code == 200
    assert response.json()["resources"]["power"]["value"] == C["resources"]["power"]["capacity"]
    assert client.post("/ingest/resource", json={"oxygen": 0}).json()["failed"]


def test_history_contains_committed_resource_event(client):
    client.post("/resources", json={"power": C["resources"]["power"]["warning"]})
    messages = client.get("/history").json()
    assert any(message["type"] == "world_event" and message["payload"]["type"] == "player_edit" for message in messages)


@pytest.mark.parametrize("number", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_numeric_resource_edit_is_rejected(client, number):
    before = client.get("/world").json()
    response = client.post("/resources", content='{"oxygen":' + number + '}',
                           headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert client.get("/world").json() == before


def test_ws_external_plan_and_thought_connections(client):
    state = client.get("/world").json()
    with client.websocket_connect("/ws") as socket:
        socket.receive_json()
        socket.send_json({"type": "submit_plan", "payload": {"tick": state["tick"], "state_version": state["version"]}})
        assert socket.receive_json()["type"] == "plan_accepted"
        socket.send_json({"type": "agent_thought", "payload": {
            "id": "ws-chat", "ts": 0, "tick": state["tick"], "agent": "human", "kind": "advice", "text": "test",
        }})
        assert socket.receive_json()["type"] == "agent_thought"
        assert client.get("/world").json() == state
