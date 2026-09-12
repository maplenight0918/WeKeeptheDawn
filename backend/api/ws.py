"""Per-client WebSocket queues, snapshot on connect, shared control services."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from backend.api.rest import Control, ResourceEdit, apply_control, apply_resources, submit_plan
from backend.domain.models import AgentThought, TickPlan

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(socket: WebSocket):
    await socket.accept()
    app = socket.app
    bus = app.state.bus
    queue = bus.subscribe()

    async def send():
        while True:
            await socket.send_json(await queue.get())

    async def receive():
        while True:
            try:
                message = await socket.receive_json()
                if not isinstance(message, dict) or set(message) != {"type", "payload"}:
                    raise ValueError("Expected an envelope with type and payload")
                kind, payload = message["type"], message["payload"]
                if kind == "control":
                    await apply_control(app, Control.model_validate(payload))
                elif kind == "edit_resources":
                    await apply_resources(app, ResourceEdit.model_validate(payload))
                elif kind == "submit_plan":
                    result = submit_plan(app, TickPlan.model_validate(payload))
                    queue.put_nowait({"type": "plan_accepted", "payload": result})
                elif kind == "agent_thought":
                    await app.state.source.relay_thought(AgentThought.model_validate(payload))
                else:
                    raise ValueError("Unknown client message type")
            except (ValidationError, ValueError, TypeError, HTTPException) as exc:
                detail = (json.loads(exc.json()) if isinstance(exc, ValidationError)
                          else exc.detail if isinstance(exc, HTTPException) else str(exc))
                queue.put_nowait({"type": "error", "payload": {"code": "INVALID_MESSAGE", "detail": detail}})

    tasks = []
    try:
        await socket.send_json({"type": "state_update", "payload": app.state.repository.get().model_dump(mode="json")})
        tasks = [asyncio.create_task(send()), asyncio.create_task(receive())]
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    except WebSocketDisconnect:
        pass
    finally:
        bus.unsubscribe(queue)
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
