from backend.domain.config import C, CROPS
from backend.engine.events import emit
from backend.engine.irrigation import irrigate


def update_crops(state, plan, summary, events):
    plots = {plot.id: plot for plot in state.plots}
    attempted = set()
    for plot in state.plots:
        plot.irrigated_last_tick = False
    for plot_id in plan.irrigation:
        plot = plots[plot_id]
        if plot.crop is None or plot.dead or plot_id in attempted:
            continue
        attempted.add(plot_id)
        summary.irrigation.attempted.append(plot_id)
        if irrigate(state, plot):
            plot.irrigated_last_tick = True
            plot.consecutive_unirrigated_ticks = 0
            crop = CROPS[plot.crop]
            plot.progress_ticks = min(crop["maturity_ticks"], plot.progress_ticks + 1)
            plot.mature = plot.progress_ticks >= crop["maturity_ticks"]
            summary.irrigation.succeeded.append(plot_id)
            summary.irrigation.water_used += C["irrigation"]["water_l"]
            summary.irrigation.power_used += C["irrigation"]["power_eu"]
            produced = crop["oxygen_per_tick"]
            room = max(0, state.resources["oxygen"].capacity - state.resources["oxygen"].value - state.pending_oxygen)
            deposited = min(produced, room)
            state.pending_oxygen += deposited
            summary.oxygen_produced += produced
            summary.oxygen_overflow += produced - deposited
    for plot in state.plots:
        if plot.crop is None or plot.dead or plot.irrigated_last_tick:
            continue
        plot.consecutive_unirrigated_ticks += 1
        summary.irrigation.failed.append(plot.id)
        count = plot.consecutive_unirrigated_ticks
        if count >= C["irrigation"]["death_after_ticks"]:
            plot.dead = True
            plot.mature = False
            summary.plots_died.append(plot.id)
            emit(state, events, "plot_died", plot.id, consecutive_unirrigated_ticks=count)
        else:
            kind = "plot_critical" if count >= C["irrigation"]["critical_after_ticks"] else "plot_unirrigated"
            emit(state, events, kind, plot.id, consecutive_unirrigated_ticks=count)
    if summary.oxygen_overflow:
        emit(state, events, "oxygen_overflow", "oxygen", produced=summary.oxygen_produced,
             deposited=summary.oxygen_produced - summary.oxygen_overflow, overflow=summary.oxygen_overflow)
