"""HTTP adapters share the loop services; no route performs resource arithmetic."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ConfigDict, Field

from backend.domain.models import AgentThought, TickPlan, WireModel, WorldEvent
from backend.integration.decisions import DecisionConflict

router = APIRouter()


class DecisionSubmission(WireModel):
    request_id: str = Field(min_length=1, max_length=128)
    submission_id: str = Field(min_length=1, max_length=128)
    plan: TickPlan


class DecisionFailure(WireModel):
    request_id: str = Field(min_length=1, max_length=128)


@router.get("/decision")
async def decision(request: Request):
    return await request.app.state.loop.decision_request()


@router.post("/ingest/decision-plan", status_code=202)
async def decision_plan(body: DecisionSubmission, request: Request):
    if request.app.state.mode != "external":
        raise HTTPException(409, "external mode required")
    try:
        return await request.app.state.loop.submit_decision(body.request_id, body.submission_id, body.plan)
    except DecisionConflict as exc:
        raise HTTPException(409, str(exc)) from None


@router.post("/ingest/decision-failure", status_code=202)
async def decision_failure(body: DecisionFailure, request: Request):
    if request.app.state.mode != "external":
        raise HTTPException(409, "external mode required")
    try:
        await request.app.state.loop.fail_decision(body.request_id)
    except DecisionConflict as exc:
        raise HTTPException(409, str(exc)) from None
    return {"accepted": True, "request_id": body.request_id}


async def request_validation_error(request: Request, error: RequestValidationError):
    # Do not echo invalid input: NaN/Infinity are precisely what was rejected,
    # and putting them in the JSON error body would turn validation into a 500.
    detail = [{key: item[key] for key in ("type", "loc", "msg") if key in item}
              for item in error.errors()]
    return JSONResponse(status_code=422, content={"detail": detail})


class ResourceEdit(WireModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)
    water: float | None = None
    oxygen: float | None = None
    food: float | None = None
    power: float | None = None


class Control(WireModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)
    cmd: Literal["pause", "resume", "speed"]
    value: float | None = None


async def apply_control(app, command: Control):
    try:
        state = await app.state.loop.control(command.cmd, command.value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if command.cmd == "resume":
        await app.state.start_loop()
    return state


async def apply_resources(app, values: ResourceEdit):
    try:
        return await app.state.loop.edit_resources(values.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def submit_plan(app, plan: TickPlan):
    if app.state.mode != "external":
        raise HTTPException(status_code=409, detail="Plan submission requires external integration mode")
    accepted = app.state.source.submit(plan)
    return {"accepted": True, "validated": False, "tick": accepted.tick,
            "state_version": accepted.state_version}


@router.get("/healthz")
async def healthz(request: Request):
    return {"status": "ok", "mode": request.app.state.mode, "planning": request.app.state.loop.planning}


@router.get("/world")
async def world(request: Request):
    return request.app.state.repository.get()


@router.post("/control")
async def control(body: Control, request: Request):
    return await apply_control(request.app, body)


@router.post("/resources")
async def resources(body: ResourceEdit, request: Request):
    return await apply_resources(request.app, body)


@router.post("/world/reset")
async def reset(request: Request):
    state = await request.app.state.loop.reset()
    await request.app.state.start_loop()
    return state


@router.get("/history")
async def history(request: Request, limit: int = Query(default=100, ge=1, le=1000)):
    return request.app.state.history.recent(limit)


@router.post("/ingest/plan", status_code=202)
async def ingest_plan(body: TickPlan, request: Request):
    return submit_plan(request.app, body)


@router.post("/ingest/thought", status_code=202)
async def ingest_thought(body: AgentThought, request: Request):
    await request.app.state.source.relay_thought(body)
    return {"accepted": True, "id": body.id}


@router.post("/ingest/resource")
async def ingest_resource(body: ResourceEdit, request: Request):
    return await apply_resources(request.app, body)


@router.post("/ingest/crew")
@router.post("/ingest/plot")
async def reject_state_patch():
    raise HTTPException(status_code=409, detail="Crew and plot state may only change through validated world settlement")


@router.post("/ingest/event", status_code=202)
async def ingest_event(body: WorldEvent, request: Request):
    # The external provenance remains visible; only state_update is authoritative.
    event = body.model_copy(deep=True)
    event.detail["source"] = "external"
    await request.app.state.bus.publish("world_event", event)
    return {"accepted": True, "id": event.id}
