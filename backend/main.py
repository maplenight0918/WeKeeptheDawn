"""FastAPI composition root. Agent decisions enter through integration adapters."""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from backend.domain.models import create_initial_state
from backend.domain.state import StateRepository
from backend.integration.sources import MockPlanSource
from backend.integration.decisions import ManagedExternalPlanSource
from backend.integration.settings import RuntimeSettings, load_runtime_settings
from backend.orchestration.event_bus import EventBus
from backend.orchestration.world_loop import WorldLoop
from backend.persistence.db import Database
from backend.persistence.repositories import WorldHistory

logger = logging.getLogger(__name__)


def create_app(mode: str = "mock", db_path: str = ":memory:", autostart: bool = True,
               runtime_settings: RuntimeSettings | None = None) -> FastAPI:
    if mode not in {"mock", "external"}:
        raise ValueError("PLAN_SOURCE must be mock or external")

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        database = Database(db_path)
        try:
            history = WorldHistory(database)
            resume = os.environ.get("RESUME_WORLD", "false").lower() in {"true", "1", "yes"}
            initial = history.latest() if resume else None
            if initial is None:
                initial = create_initial_state()
            history.save(initial)
            repository = StateRepository(initial, persist=history.save)
            bus = EventBus(record=history.record)
            configured = runtime_settings or RuntimeSettings(plan_source=mode)
            source = (MockPlanSource(bus) if mode == "mock" else ManagedExternalPlanSource(
                bus, timeout_seconds=configured.decision_timeout_seconds))
            loop = WorldLoop(repository, bus, source)
            start_lock = asyncio.Lock()
            application.state.repository = repository
            application.state.history = history
            application.state.bus = bus
            application.state.source = source
            application.state.loop = loop
            application.state.mode = mode
            application.state.runtime_settings = runtime_settings or RuntimeSettings(plan_source=mode)
            application.state.autostart = autostart
            application.state.runner = None

            def completed(task):
                if not task.cancelled() and task.exception() is not None:
                    logger.error("World runner stopped with an error", exc_info=task.exception())

            async def start_loop():
                if not autostart:
                    return
                async with start_lock:
                    running = application.state.runner
                    if running is None or running.done():
                        running = asyncio.create_task(loop.run(), name="space-greenhouse-world")
                        running.add_done_callback(completed)
                        application.state.runner = running

            application.state.start_loop = start_loop
            await start_loop()
            try:
                yield
            finally:
                await loop.stop()
                running = application.state.runner
                if running is not None and not running.done():
                    running.cancel()
                    await asyncio.gather(running, return_exceptions=True)
        finally:
            database.close()

    application = FastAPI(title="Space Greenhouse", lifespan=lifespan)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173", "http://127.0.0.1:5173",
            "http://localhost:5174", "http://127.0.0.1:5174",
            "http://localhost:5175", "http://127.0.0.1:5175",
        ],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    from backend.api.rest import router as rest_router
    from backend.api.rest import request_validation_error
    from backend.api.ws import router as ws_router

    application.include_router(rest_router)
    application.include_router(ws_router)
    application.add_exception_handler(RequestValidationError, request_validation_error)
    return application


runtime_settings = load_runtime_settings()
app = create_app(mode=runtime_settings.plan_source,
                 db_path=os.environ.get("WORLD_DB", "backend/data/world.sqlite3"), runtime_settings=runtime_settings)
