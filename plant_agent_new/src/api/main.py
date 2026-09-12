"""Run with python -m uvicorn src.api.main:app --port 8000."""
import math
import asyncio
import sys
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from paths import ROOT
from src.agent.plant_agent import analyze
from src.agent.discussion import discuss
from src.api.discussion_schema import DiscussInput, DiscussOutput
from src.api.schema import (Crop, PlantAgentInput, PlantAgentOutput, SearchResult,
                            SimulateOutput, SweepRow, WorldCropsOutput)
from src.models.coefficients import Coefficients
from src.models.greenhouse import simulate, sweep_ppfd
from src.retrieval.embedder import ProviderError
from src.retrieval.store import CorpusStore


@asynccontextmanager
async def lifespan(app):
    app.state.store = CorpusStore()
    yield
    del app.state.store


app = FastAPI(title="Plant Agent API", lifespan=lifespan)


@app.post("/discuss", response_model=DiscussOutput)
async def discuss_endpoint(inp: DiscussInput, request: Request):
    try:
        return await asyncio.wait_for(asyncio.to_thread(discuss, request.app.state.store, inp), timeout=120)
    except TimeoutError:
        raise HTTPException(504, "Plant 討論逾時，請保持世界暫停。")


@app.exception_handler(ProviderError)
async def provider_error(request: Request, exc: ProviderError):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.get("/health")
def health(request: Request):
    return {"status": "ok", "chunks": len(request.app.state.store.chunks)}


@app.post("/simulate", response_model=SimulateOutput)
def simulate_endpoint(inp: PlantAgentInput):
    return simulate(Coefficients(inp.crop), inp)


@app.post("/analyze", response_model=PlantAgentOutput)
def analyze_endpoint(inp: PlantAgentInput, request: Request):
    return analyze(request.app.state.store, inp)


@app.post("/sweep", response_model=list[SweepRow])
def sweep_endpoint(inp: PlantAgentInput, levels: str = "0.6,0.8,1.0,1.2,1.5"):
    try:
        multipliers = [float(x.strip()) for x in levels.split(",")]
        if not 1 <= len(multipliers) <= 100 or any(not math.isfinite(x) or x < 0 for x in multipliers):
            raise ValueError
        points = [inp.ppfd * x for x in multipliers]
        if any(not math.isfinite(x) for x in points):
            raise ValueError
    except ValueError:
        raise HTTPException(422, "levels 必須為 1–100 個有限、非負的倍率，以逗號分隔。")
    return sweep_ppfd(Coefficients(inp.crop), inp, points)


@app.get("/search", response_model=list[SearchResult])
def search_endpoint(request: Request, q: str = Query(..., min_length=1),
                    k: int = Query(8, ge=1, le=100), crop: Crop | None = None,
                    units: str | None = None, tier: str = "A_plant_core,B_usable"):
    def split(value):
        return [x.strip() for x in value.split(",") if x.strip()] if value else None
    hits = request.app.state.store.search(q, k=k, tiers=split(tier),
                                         crops=[crop] if crop else None, units=split(units))
    return [asdict(hit) for hit in hits]


@app.get("/world/crops", response_model=WorldCropsOutput)
def world_crops():
    conditions = PlantAgentInput()
    crops = []
    for crop in ["lettuce", "potato", "tomato", "wheat", "soybean"]:
        result = simulate(Coefficients(crop), conditions.model_copy(update={"crop": crop}))
        crops.append({"crop": crop, "edible_g_m2_day": result["supply"]["edible_g_day"] / 20,
                      "o2_g_m2_day": result["supply"]["o2_kg_day"] * 1000 / 20,
                      "coefficients": result["coefficients"]})
    return {"conditions": conditions, "crops": crops,
            "note": "固定條件下的文獻係數與模型換算，供前端解釋出處；不參與世界結算。"}
