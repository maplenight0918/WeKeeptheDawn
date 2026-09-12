"""Explicit integration fixtures, NEVER used as a live failure fallback."""
from core_agent.core_agent.contracts import Message, empty_explanation


class FixtureSpecialist:
    async def ask(self, request):
        explanation = empty_explanation()
        explanation["observations"] = ["展示 fixture：收到同版本快照及權威規則。"]
        return Message(request.discussion_id, request.round, request.recipient, "core", request.world_version,
                       {key: [] for key in ("observations", "priorities", "suggested_actions",
                                             "acceptable_tradeoffs", "evidence_and_unknowns")},
                       display_text="展示 fixture：請 Core 納入本輪討論；未呼叫模型。", explanation=explanation)


class FixtureModel:
    async def decide(self, context):
        explanation = empty_explanation()
        explanation["decision_reason"] = "展示 fixture：只驗證灌溉及結算回傳，不代表生存策略。"
        world = context["world"]
        return {"kind": "final", "summary": "展示 fixture：本 tick 安排完整灌溉，其餘不執行。",
                "plant_question": "", "human_question": "", "explanation": explanation,
                "plan": {"plan_id": f"fixture-{world['world_version']}", "rules_version": world["rules_version"],
                         "based_on_state_version": world["world_version"], "reason": explanation["decision_reason"],
                         "entry_stage_id": "fixture", "stages": [{"stage_id": "fixture", "purpose": "測試",
                             "max_ticks": 1, "water_liters_per_tick": 0,
                             "irrigation_order": [p["id"] for p in world["plots"] if p["status"] in {"growing", "mature"}],
                             "actions": [], "transitions": []}]}}


class ActionFixtureModel(FixtureModel):
    """Opt-in visual demo schedule, never a live strategy or failure fallback.

    Uses actual observed plots; maturity and inventory are never manufactured.
    The seven-tick crew tape is intentionally fixed, not an adaptive policy.
    """

    cycle = ("drink", "generate", "eat", "generate", "drink", "generate", "eat")

    async def decide(self, context):
        result = await super().decide(context)
        world, rules = context["world"], context["rules"]
        stage = result["plan"]["stages"][0]
        jobs = []
        for plot in world["plots"]:
            if plot["status"] == "empty":
                jobs.append(("plant", plot["id"], "lettuce"))
            elif plot["status"] == "dead":
                jobs.append(("clear", plot["id"], None))
            elif plot["status"] == "mature":
                jobs.append(("harvest", plot["id"], None))
        # One explicitly scripted early clear, not a recurring clear/replant loop.
        if world["tick"] == 0:
            last_plot = world["plots"][-1]
            if last_plot["status"] == "growing":
                jobs.insert(0, ("clear", last_plot["id"], None))
        actions = []
        for index, crew in enumerate(world["crew"]):
            if not crew["alive"]:
                continue
            kind = self.cycle[(world["tick"] + index) % len(self.cycle)]
            plot_id = crop = None
            if kind == "generate" and jobs:
                kind, plot_id, crop = jobs.pop(0)
            amount = (rules["crew"]["refill_limit"][kind] if kind in {"eat", "drink"}
                      else rules["generation"]["max_units_per_crew_tick"] if kind == "generate" else 1)
            actions.append({"action_id": f"demo-{world['tick']}-{crew['id']}",
                            "crew_id": crew["id"], "kind": kind, "tick_offset": 0,
                            "repeat": False, "plot_id": plot_id, "crop_type": crop, "amount": amount})
        stage["actions"] = actions
        stage["water_liters_per_tick"] = min(
            rules["water_production"]["max_L_per_tick"],
            len(stage["irrigation_order"]) * rules["irrigation"]["water_per_plot"]
            + sum(a["amount"] for a in actions if a["kind"] == "drink"))
        description = "、".join(f"{a['crew_id']} {a['kind']}" + (f" {a['plot_id']}" if a["plot_id"] else "")
                               for a in actions)
        reason = "展示 fixture：固定輪班與地塊操作，驗證設備及動畫；非真實 Agent 生存策略。"
        result["explanation"]["decision_reason"] = reason
        result["plan"]["reason"] = reason
        result["plan"]["plan_id"] = f"action-fixture-{world['world_version']}"
        stage["purpose"] = "完整動作展示"
        result["summary"] = f"完整動作 fixture：{description}；製水 {stage['water_liters_per_tick']:g} L、灌溉。"
        return result
