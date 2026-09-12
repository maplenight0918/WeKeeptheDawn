"""Shared snake_case wire models. World coefficients live in shared JSON only."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class WireModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ResourceState(WireModel):
    key: str
    unit: str
    value: float
    capacity: float
    warning: float


class Plot(WireModel):
    id: str
    crop: str | None = None
    progress_ticks: int = 0
    mature: bool = False
    dead: bool = False
    consecutive_unirrigated_ticks: int = 0
    irrigated_last_tick: bool = False


class CrewState(WireModel):
    id: str
    name: str
    food_energy: float
    water: float
    alive: bool = True
    death_reason: Literal["food_energy", "water", "oxygen"] | None = None
    location: str = "quarters"
    current_task: Literal[
        "idle", "walking", "generating", "water_plant", "irrigation_console",
        "planting", "harvesting", "clearing", "eating", "drinking", "dead",
    ] = "idle"
    work_this_tick: float = 0


class Refill(WireModel):
    # TODO(guide-pending): formal tool interface; this is the minimum plan payload.
    # Array position expresses Core order, amount expresses its requested share.
    crew_id: str
    kind: Literal["food", "water"]
    amount: float


class PlotOp(WireModel):
    order: int
    crew_id: str
    plot_id: str
    op: Literal["plant", "harvest", "clear"]
    crop: str | None = None


class TickPlan(WireModel):
    tick: int
    # Version binds a decision to its observed snapshot; never a resource amount.
    state_version: int | None = None
    refills: list[Refill] = Field(default_factory=list)
    generation: dict[str, float] = Field(default_factory=dict)
    water_production_l: float = 0
    irrigation: list[str] = Field(default_factory=list)
    plot_ops: list[PlotOp] = Field(default_factory=list)
    rationale: str = ""


class GenerationSummary(WireModel):
    requested: float = 0
    actual: float = 0
    power_out: float = 0
    oxygen_used: float = 0


class WaterPlantSummary(WireModel):
    requested: float = 0
    actual: float = 0
    power_used: float = 0
    oxygen_used: float = 0


class IrrigationSummary(WireModel):
    attempted: list[str] = Field(default_factory=list)
    succeeded: list[str] = Field(default_factory=list)
    failed: list[str] = Field(default_factory=list)
    water_used: float = 0
    power_used: float = 0


class Harvested(WireModel):
    plot_id: str
    crop: str
    food: float


class Planted(WireModel):
    plot_id: str
    crop: str


class Death(WireModel):
    crew_id: str
    reason: str


class TickSummary(WireModel):
    tick: int
    refills: list[Refill] = Field(default_factory=list)
    generation: GenerationSummary = Field(default_factory=GenerationSummary)
    water_plant: WaterPlantSummary = Field(default_factory=WaterPlantSummary)
    irrigation: IrrigationSummary = Field(default_factory=IrrigationSummary)
    oxygen_produced: float = 0
    oxygen_overflow: float = 0
    harvested: list[Harvested] = Field(default_factory=list)
    planted: list[Planted] = Field(default_factory=list)
    cleared: list[str] = Field(default_factory=list)
    plots_died: list[str] = Field(default_factory=list)
    deaths: list[Death] = Field(default_factory=list)


class ContinuousSettings(WireModel):
    water_production_l: float = 0
    generation: dict[str, float] = Field(default_factory=dict)
    irrigation: list[str] = Field(default_factory=list)


class WorldState(WireModel):
    version: int = 0
    tick: int = 0
    paused: bool = False
    paused_reason: Literal["player", "planning", "error"] | None = None
    speed: float = 1
    failed: bool = False
    failure_reason: str | None = None
    resources: dict[str, ResourceState]
    pending_oxygen: float = 0
    pending_food: float = 0
    plots: list[Plot]
    crew: dict[str, CrewState]
    settings: ContinuousSettings = Field(default_factory=ContinuousSettings)
    last_summary: TickSummary | None = None


class AgentThought(WireModel):
    id: str
    ts: float
    tick: int
    agent: Literal["core", "plant", "human"]
    kind: Literal["observe", "risk", "advice", "plan", "validation_error", "reflection"]
    text: str
    payload: Any = None


class WorldEvent(WireModel):
    id: str
    tick: int
    type: Literal[
        "crew_low_supply", "resource_low", "plot_unirrigated", "plot_critical",
        "plot_died", "oxygen_overflow", "harvest_blocked_capacity", "crew_died",
        "mission_failed", "plan_failed", "player_edit",
    ]
    target: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class ValidationError(WireModel):
    code: str
    target: str | None = None
    message: str


def create_initial_state() -> WorldState:
    """Guide initial snapshot. Empty settings are intentional, not a Core policy."""
    from backend.domain.config import C, CROPS

    resources = {
        key: ResourceState(key=key, unit=config["unit"], value=config["initial"],
                           capacity=config["capacity"], warning=config["warning"])
        for key, config in C["resources"].items()
    }
    # This is map initialization, never an irrigation or work allocation order.
    initial_crops = [key for key in CROPS for _ in range(C["plots"]["initial_per_crop"])]
    plots = [
        Plot(id=f"p{index + 1:02d}", crop=initial_crops[index] if index < len(initial_crops) else None)
        for index in range(C["plots"]["count"])
    ]
    crew = {}
    for index in range(C["crew"]["count"]):
        crew_id = f"c{index + 1:02d}"
        crew[crew_id] = CrewState(id=crew_id, name=f"Crew {index + 1}",
                                 food_energy=C["crew"]["food_energy"]["initial"],
                                 water=C["crew"]["water"]["initial"])
    return WorldState(resources=resources, plots=plots, crew=crew)


def tick_plan_schema() -> dict[str, Any]:
    """Provider schema generated from models and the live crop catalog."""
    from backend.domain.config import CROPS

    schema = TickPlan.model_json_schema()
    schema["$defs"]["PlotOp"]["properties"]["crop"]["anyOf"][0]["enum"] = list(CROPS)
    return schema
