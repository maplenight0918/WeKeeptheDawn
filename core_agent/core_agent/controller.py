"""Always-on Core controller; the world adapter owns simulation and atomic writes."""
import asyncio
from copy import deepcopy
from typing import Protocol
from .contracts import obj, STRING, validate_shape, validate_world
from .orchestrator import PlanningError

ASSESSMENT_SCHEMA = obj({
    'decision': {'type': 'string', 'enum': ['continue', 'replan']},
    'reason': STRING,
})


class WorldPort(Protocol):
    async def observe(self) -> dict:
        """Atomic between-ticks snapshot with actual world_status and crew alive.
        World starts running; observing or periodic assessment must not pause time.
        Include current_plan, replan_required and recent_events when available.
        """
        ...

    async def pause_for_core(self, expected_version: int) -> dict | None:
        """CAS: acquire pause; return fresh snapshot plus pause_token, or None.
        Must not acquire a world manually paused, failed or owned by another controller.
        """
        ...

    async def apply_and_resume(self, plan: dict, expected_version: int, pause_token: str) -> bool:
        """Atomically validate version+ownership, apply plan and release ONLY Core pause.
        False means state/ownership changed; never override a player's pause.
        """
        ...


class CoreController:
    def __init__(self, core, world: WorldPort, rules, *, poll_seconds=.5,
                 assessment_every_ticks=1, assessment_timeout=60, on_event=None):
        if poll_seconds <= 0 or assessment_every_ticks < 1 or assessment_timeout <= 0:
            raise ValueError('controller intervals must be positive')
        self.core, self.world, self.rules = core, world, deepcopy(rules)
        self.poll_seconds, self.assessment_every_ticks = poll_seconds, assessment_every_ticks
        self.assessment_timeout, self.on_event = assessment_timeout, on_event
        self._previous = None
        self._assessment = None
        self._last_assessment_tick = None
        self._history = []
        self._lock = asyncio.Lock()
        self._pending_reason = None

    def _emit(self, kind, **payload):
        if self.on_event:
            self.on_event({'type': kind, **payload})

    def _risk(self, state):
        if state.get('replan_required') or state.get('current_plan') is None:
            return 'world requests reassessment or no active plan'
        previous = self._previous
        for name, settings in self.rules['resources'].items():
            value = state['resources'][name]
            old = previous['resources'][name] if previous else float('inf')
            if value < settings['warning'] and value < old:
                return f'{name} low or worsening'
        old_crew = {c['id']: c for c in previous['crew']} if previous else {}
        for person in state['crew']:
            for name, warning in self.rules['crew']['warning'].items():
                if person[name] < warning and person[name] < old_crew.get(person['id'], {}).get(name, float('inf')):
                    return f'{person["id"]}.{name} low or worsening'
        old_plots = {p['id']: p for p in previous['plots']} if previous else {}
        for plot in state['plots']:
            old = old_plots.get(plot['id'], {})
            if plot['consecutive_unirrigated_ticks'] > old.get('consecutive_unirrigated_ticks', 0):
                return f'{plot["id"]} irrigation interrupted'
            if plot['status'] == 'dead' and old.get('status') != 'dead':
                return f'{plot["id"]} died'
        return None

    async def _cancel_assessment(self):
        if self._assessment is not None:
            task, self._assessment = self._assessment, None
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def _plan_and_apply(self, observed, reason):
        await self._cancel_assessment()
        frozen = await self.world.pause_for_core(observed['world_version'])
        if frozen is None:
            self._pending_reason = reason
            self._emit('pause_conflict', world_version=observed['world_version'])
            return
        self._pending_reason = None
        self._emit('planning_started', world_version=frozen['world_version'], reason=reason)
        try:
            result = await self.core.plan(frozen, self.rules, reason=reason,
                current_plan=frozen.get('current_plan'), history=list(self._history),
                on_event=self.on_event)
            applied = await self.world.apply_and_resume(result.plan, frozen['world_version'], frozen['pause_token'])
            self._emit('plan_applied' if applied else 'plan_rejected_stale',
                       discussion_id=result.discussion_id, world_version=frozen['world_version'])
        except Exception:
            self._emit('planning_failed', world_version=frozen['world_version'])
            # World remains paused: never auto-resume without a valid acknowledged plan.
            raise

    async def step(self):
        """One observation; serialize callers, and never block monitoring on a GPT assessment."""
        async with self._lock:
            state = deepcopy(await self.world.observe())
            validate_world(state)
            if state['world_status'] == 'failed' or any(not c['alive'] for c in state['crew']):
                await self._cancel_assessment()
                return False
            if state['world_status'] != 'running':
                await self._cancel_assessment()
                return True  # Respect player/error pauses; don't take over ownership.
            if state['rules_version'] != self.rules['rules_version']:
                raise PlanningError('controller rules mismatch')
            reason = self._pending_reason or self._risk(state)
            if self._previous is None or state['world_version'] != self._previous['world_version']:
                self._history.append({'world_version': state['world_version'], 'tick': state['tick'],
                                      'resources': state['resources'], 'events': state.get('recent_events', [])})
                self._history = self._history[-24:]
            self._previous = state
            if reason:
                await self._plan_and_apply(state, reason)
                return True
            if self._assessment is not None and self._assessment.done():
                task, self._assessment = self._assessment, None
                try:
                    assessment = task.result()
                    validate_shape(assessment, ASSESSMENT_SCHEMA)
                except Exception:
                    self._emit('assessment_failed')
                    # Assessment failure warrants a frozen, full retry, never blind execution.
                    await self._plan_and_apply(state, 'periodic assessment failed')
                    return True
                self._emit('assessment_completed', **assessment)
                if assessment['decision'] == 'replan':
                    # This is a signal only. Replan against a NEW frozen snapshot, not the old one.
                    await self._plan_and_apply(state, assessment['reason'])
                    return True
            due = self._last_assessment_tick is None or state['tick'] >= self._last_assessment_tick + self.assessment_every_ticks
            if self._assessment is None and due:
                self._last_assessment_tick = state['tick']
                context = {'world': deepcopy(state), 'rules': self.rules, 'history': list(self._history)}
                self._assessment = asyncio.create_task(self._assess(context))
                self._emit('assessment_started', world_version=state['world_version'])
            return True

    async def _assess(self, context):
        return await asyncio.wait_for(self.core.model.assess(context), self.assessment_timeout)

    async def run(self, stop: asyncio.Event):
        """Long-lived Core-owned loop. A host starts it once, not once per emergency."""
        try:
            while not stop.is_set() and await self.step():
                try:
                    await asyncio.wait_for(stop.wait(), timeout=self.poll_seconds)
                except asyncio.TimeoutError:
                    pass
        finally:
            await self._cancel_assessment()
