"""Lossless snapshot mapping and explicit current-stage action translation."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import time

from backend.domain.config import C, CROPS, RAW_CONSTANTS, RAW_CROPS, crew_consumption_per_tick, harvest_food
from backend.domain.models import AgentThought, TickPlan, WorldState
from core_agent.core_agent.contracts import EXPLANATION_SCHEMA, validate_plan, validate_shape, validate_world


class BridgeContractError(ValueError):
    pass


def game_rules():
    """Map authoritative shared parameters to the specialist DTO, never Core's copy."""
    fingerprint = hashlib.sha256(json.dumps([RAW_CONSTANTS, RAW_CROPS], sort_keys=True).encode()).hexdigest()[:16]
    crew, generation, water = C["crew"], C["generation"], C["water_plant"]
    return {
        "rules_version": f"space-greenhouse-pending-v1-{fingerprint}",
        "tick_hours": C["time"]["simulation_hours_per_tick"],
        "environment": {"carbon_dioxide": {"value": C["environment"]["co2_ppm"], "unit": "ppm", "adjustable": False}},
        "resources": {key: {"unit": RAW_CONSTANTS["resources"][key]["capacity"]["unit"],
                            "capacity": value["capacity"], "warning": value["warning"]}
                      for key, value in C["resources"].items()},
        "crew": {
            "daily_reference": {"kcal": crew["daily_consumption"]["food_energy"],
                                "oxygen_kg": crew["daily_consumption"]["oxygen_kg"],
                                "water_L": crew["daily_consumption"]["water"]},
            "per_tick": crew_consumption_per_tick(),
            "capacity": {key: crew[key]["capacity"] for key in ("food_energy", "water")},
            "warning": {key: crew[key]["warning"] for key in ("food_energy", "water")},
            "refill_limit": {"eat": crew["food_energy"]["refill_max"], "drink": crew["water"]["refill_max"]},
            "refill_ratio": crew["conversion"]["refill_ratio"],
            "death": "personal energy or water <= 0; any crew death ends mission",
        },
        "generation": {"food_energy": generation["food_energy_per_work"], "oxygen": generation["oxygen_per_work"],
                       "power": generation["power_per_work"], "max_units_per_crew_tick": generation["max_work_per_crew"],
                       "stations": generation["stations"]},
        "water_production": {"power_per_L": water["power_per_l"], "oxygen_per_L": water["oxygen_per_l"],
                             "max_L_per_tick": water["max_l_per_tick"]},
        "irrigation": {"water_per_plot": C["irrigation"]["water_l"], "power_per_plot": C["irrigation"]["power_eu"],
                       "atomic_inputs": True, "misses_until_death": C["irrigation"]["death_after_ticks"],
                       "priority": "Core supplied order; omitted living plots receive nothing",
                       "failure": "no input deducted, no growth or oxygen; success resets misses",
                       "dead": "no consumption or yield; clear before planting"},
        "crops": {key: {"maturity_ticks": crop["maturity_ticks"], "harvest_game_kcal": harvest_food(key),
                        "oxygen_per_tick": crop["oxygen_per_tick"]} for key, crop in CROPS.items()},
        "tasks": {"occupancy": "eat, drink, generate, plant, harvest, clear: one crew per tick",
                  "controls_and_movement": "visual only, no occupancy",
                  "crop_actions": "at tick end, ordered; no premature harvest; full storage blocks harvest",
                  "plant": "empty plot only; no seed cost; starts growing next tick"},
        "oxygen_death": "public oxygen <= 0 immediately kills all crew, even before plants produce oxygen",
        "tick_order": ["ordered refill", "personal metabolism", "public breathing", "generation",
                       "water production", "ordered irrigation", "ordered crop actions"],
        "planning": "world paused while planning; validate state version before apply; no simulator",
        "completion": "no stable/success threshold; continue until death",
        "metadata": {
            "authority": "root world-settings-guide.md + shared JSON + docs/tick_order.md",
            "shared_constants": deepcopy(RAW_CONSTANTS), "shared_crops": deepcopy(RAW_CROPS),
            "pending": "Pending reserves capacity, remains separate at observation, merges only inside the next engine settlement before refills.",
            "control": "WorldLoop waits without advancing ticks; this is not a player/planning pause transition.",
            "electricity": "Use shared irrigation cost; the Plant physical electricity conversion is not an approved runtime rule.",
        },
    }


def core_snapshot(state: WorldState, rules: dict) -> dict:
    snapshot = state.model_dump(mode="json")
    snapshot.update(
        world_version=state.version, rules_version=rules["rules_version"], snapshot_phase="between_ticks",
        world_status=("failed" if state.failed else "error_paused" if state.paused_reason == "error"
                      else "planning" if state.paused_reason == "planning" else "paused" if state.paused else "running"),
        resource_details=deepcopy(snapshot["resources"]),
        resources={key: resource.value for key, resource in state.resources.items()},
        crew=[crew.model_dump(mode="json") for crew in state.crew.values()],
        plots=[{**plot.model_dump(mode="json"), "crop_type": plot.crop,
                "growth_ticks": plot.progress_ticks,
                "status": "dead" if plot.dead else "empty" if plot.crop is None else "mature" if plot.mature else "growing"}
               for plot in state.plots],
    )
    validate_world(snapshot)
    return snapshot


def current_tick_plan(plan: dict, snapshot: dict) -> TickPlan:
    """A freshly issued Core entry stage starts at offset zero. Never advance stages."""
    validate_plan(plan, snapshot)
    stage = next(stage for stage in plan["stages"] if stage["stage_id"] == plan["entry_stage_id"])
    generation, refills, operations = {}, [], []
    for order, action in enumerate(stage["actions"]):
        if action["tick_offset"] != 0:
            continue
        kind = action["kind"]
        if kind == "generate":
            generation[action["crew_id"]] = action["amount"]
        elif kind in {"eat", "drink"}:
            refills.append({"crew_id": action["crew_id"], "kind": "food" if kind == "eat" else "water",
                            "amount": action["amount"]})
        else:
            operations.append({"order": order, "crew_id": action["crew_id"], "plot_id": action["plot_id"],
                               "op": kind, "crop": action["crop_type"]})
    return require_tick_plan({"tick": snapshot["tick"], "state_version": snapshot["world_version"],
                             "generation": generation, "water_production_l": stage["water_liters_per_tick"],
                             "irrigation": stage["irrigation_order"], "refills": refills, "plot_ops": operations,
                             "rationale": plan["reason"]}, snapshot["tick"], snapshot["world_version"])


def require_tick_plan(data: dict, tick: int, version: int) -> TickPlan:
    required = {"tick", "state_version", "generation", "water_production_l", "irrigation", "refills", "plot_ops"}
    if not isinstance(data, dict) or not required <= data.keys():
        raise BridgeContractError("Core must explicitly supply every TickPlan action/setting field")
    if (data["tick"], data["state_version"]) != (tick, version):
        raise BridgeContractError("Core plan is stale")
    return TickPlan.model_validate(data, strict=True)


class ThoughtMapper:
    def __init__(self, state: WorldState, *, mock=False):
        self.state, self.mock = state, mock
        self.requests = {}

    def map(self, message: dict) -> AgentThought:
        if message["world_version"] != self.state.version:
            raise BridgeContractError("stale public message")
        sender, recipient = message["sender"], message["recipient"]
        content = message["content"]
        kind = ("advice" if sender != "core" else "plan" if content.get("kind") == "final"
                else "risk" if content.get("kind") == "consult" else "observe")
        metadata = {"conversation_id": message["discussion_id"], "to": recipient,
                    "round": message["round"], "world_version": self.state.version,
                    "source": "three_agent_bridge", "mock": self.mock}
        key = (message["discussion_id"], message["round"])
        if sender == "core" and recipient in {"plant", "human"}:
            self.requests[(*key, recipient)] = message["message_id"]
        elif sender in {"plant", "human"}:
            metadata["reply_to"] = self.requests.get((*key, sender))
        explanation = message.get("explanation")
        if explanation is not None:
            validate_shape(explanation, EXPLANATION_SCHEMA)
            metadata["explanation"] = deepcopy(explanation)
        return AgentThought(id=message["message_id"], ts=time.time(), tick=self.state.tick,
                            agent=sender, kind=kind, text=("[MOCK] " if self.mock else "") + message["display_text"],
                            payload=metadata)
