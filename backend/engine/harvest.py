from backend.domain.config import CROPS, harvest_food
from backend.domain.models import Harvested, Planted, ValidationError
from backend.engine.events import emit


def validate_plot_op(state, op):
    plot = next((plot for plot in state.plots if plot.id == op.plot_id), None)
    code = None
    if plot is None:
        code = "PLOT_UNKNOWN"
    elif op.op == "plant" and op.crop not in CROPS:
        code = "CROP_UNKNOWN"
    elif op.op == "plant" and plot.dead:
        code = "PLOT_DEAD_NEEDS_CLEAR"
    elif op.op == "plant" and plot.crop is not None:
        code = "PLOT_NOT_EMPTY"
    elif op.op == "harvest" and (plot.crop is None or plot.dead or not plot.mature):
        code = "PLOT_NOT_MATURE"
    return [ValidationError(code=code, target=op.plot_id, message=f"{op.op}: {code}")] if code else []


def execute_plot_ops(state, plan, summary, events, errors):
    plots = {plot.id: plot for plot in state.plots}
    for op in sorted(plan.plot_ops, key=lambda item: item.order):
        current_errors = validate_plot_op(state, op)
        if current_errors:
            errors.extend(current_errors)
            continue
        plot = plots[op.plot_id]
        crew = state.crew[op.crew_id]
        crew.current_task = {"plant": "planting", "harvest": "harvesting", "clear": "clearing"}[op.op]
        crew.location = f"plot:{plot.id}"
        if op.op == "harvest":
            food = harvest_food(plot.crop)
            resource = state.resources["food"]
            if resource.capacity - resource.value - state.pending_food < food:
                emit(state, events, "harvest_blocked_capacity", plot.id, requested=food)
                continue
            state.pending_food += food
            summary.harvested.append(Harvested(plot_id=plot.id, crop=plot.crop, food=food))
        elif op.op == "plant":
            summary.planted.append(Planted(plot_id=plot.id, crop=op.crop))
        else:
            summary.cleared.append(plot.id)
        plot.crop = op.crop if op.op == "plant" else None
        plot.progress_ticks = 0
        plot.mature = False
        plot.dead = False
        plot.consecutive_unirrigated_ticks = 0
        plot.irrigated_last_tick = False
