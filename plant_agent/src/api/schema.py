"""Public API contracts (SPEC §3)."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

Crop = Literal["lettuce", "potato", "tomato", "wheat", "soybean", "radish", "spinach", "rice", "kale", "pepper", "spirulina"]


class PlantAgentInput(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    crop: Crop = "lettuce"
    ppfd: float = Field(250, ge=0, le=2000)
    photoperiod: float = Field(14, ge=0, le=24)
    temperature: float = Field(22, ge=-10, le=60)
    humidity: float = Field(65, ge=0, le=100)
    co2: float = Field(500, ge=100, le=5000)
    area: float = Field(20, gt=0, le=10000)
    density: float = Field(27, gt=0, le=500)
    power_budget: float | None = Field(None, ge=0)


class Supply(BaseModel):
    o2_kg_day: float
    edible_g_day: float
    biomass_g_day: float
    dry_biomass_g_day: float
    water_recycled_l_day: float


class Demand(BaseModel):
    power_kw: float
    water_l_day: float
    co2_kg_day: float


class CoefficientInfo(BaseModel):
    value: float
    unit: str
    source: str
    note: str = ""


class Evidence(BaseModel):
    doc_id: str
    source: str
    title: str
    year: str = ""
    section: str = ""
    score: float


class SimulateOutput(BaseModel):
    supply: Supply
    demand: Demand
    health: float
    daily_rate: dict[str, float]
    factors: dict[str, float]
    intermediate: dict[str, float]
    warnings: list[str] = Field(default_factory=list)
    coefficients: dict[str, CoefficientInfo] = Field(default_factory=dict)


class PlantAgentOutput(BaseModel):
    supply: Supply
    demand: Demand
    health: float
    daily_rate: dict[str, float]
    reasoning: str
    tradeoff: str
    risks: list[str]
    citations: list[str]
    coefficients: dict[str, CoefficientInfo]
    factors: dict[str, float]
    warnings: list[str]
    evidence: list[Evidence]


class SweepRow(BaseModel):
    ppfd: float
    power_kw: float
    edible_g_day: float
    o2_kg_day: float
    water_l_day: float
    health: float
    power_delta_pct: float | None = None
    edible_delta_pct: float | None = None


class SearchResult(Evidence):
    text: str
    units: list[str] = Field(default_factory=list)
    crops: list[str] = Field(default_factory=list)


class WorldCrop(BaseModel):
    crop: Crop
    edible_g_m2_day: float
    o2_g_m2_day: float
    coefficients: dict[str, CoefficientInfo]


class WorldCropsOutput(BaseModel):
    conditions: PlantAgentInput
    crops: list[WorldCrop]
    note: str
