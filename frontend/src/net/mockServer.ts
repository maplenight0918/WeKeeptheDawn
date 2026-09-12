import recording from '../../../backend/fixtures/demo_states.json';
import timeline_recording from '../../../backend/fixtures/mock_timeline.json';
import { C } from '../config';
import type { AgentThought, TickPlan, WorldState } from '../../../shared/types';

export type Envelope = { type: string; payload: unknown };
type RecordedThought = { local_id?: string; agent: AgentThought['agent']; kind: AgentThought['kind']; text: string; payload?: Record<string, unknown> };
type Frame = { label: string; state: WorldState; plan: TickPlan | null; thoughts: RecordedThought[] };
const recorded = recording as unknown as { frames: Frame[]; failure?: Frame };
const timeline = timeline_recording as unknown as { frames: Frame[] };
// The opening frames retain the recorded agent conversation. Later frames are
// exact backend snapshots, not frontend simulation, so the world clock can run.
const regular = timeline.frames.filter((frame) => frame.state.tick > 2);
const frames = recorded.failure ? [...recorded.frames, ...regular, recorded.failure] : [...recorded.frames, ...regular];
let active: MockReplay | null = null;

class MockReplay {
  private timers = new Set<ReturnType<typeof setTimeout>>();
  private version = 0;
  private epoch = 0;
  private paused = false;
  private speed = 1;
  private current = frames[0];
  constructor(private emit: (envelope: Envelope) => void) {}
  private schedule(fn: () => void, delay: number) {
    const epoch = this.epoch;
    const timer = setTimeout(() => {
      this.timers.delete(timer);
      // A timeout may already be queued by the browser when pause, reset, or
      // speed changes clear the set. Never let that stale playback mutate state.
      if (epoch === this.epoch) fn();
    }, delay / this.speed);
    this.timers.add(timer);
  }
  stop() { this.epoch++; this.timers.forEach(clearTimeout); this.timers.clear(); }
  private snapshot(frame: Frame) {
    this.current = frame;
    // Only transport/control metadata changes. Resources and crew are exact recordings.
    this.emit({ type: 'state_update', payload: { ...structuredClone(frame.state), version: ++this.version,
      paused: this.paused, paused_reason: this.paused ? 'player' : null, speed: this.speed } });
  }
  private playback(frame: Frame) {
    const epoch = this.epoch;
    const decision_tick = frame.plan?.tick ?? frame.state.tick;
    const conversation_id = `mock-${epoch}-${decision_tick}-${this.version}`;
    const ids = Object.fromEntries(frame.thoughts.map((thought, index) => [thought.local_id ?? `${index}`, `${conversation_id}-${index}`]));
    frame.thoughts.forEach((thought, index) => this.schedule(() => {
      if (epoch !== this.epoch || this.paused) return;
      if (thought.kind === 'reflection') {
        this.snapshot(frame);
        if (frame.label === 'recovered') this.continue_playback();
      }
      const payload = { ...thought.payload, conversation_id, mock: true, sender: thought.agent, avatar: thought.agent,
        reply_to: typeof thought.payload?.reply_to === 'string' ? ids[thought.payload.reply_to] : null,
        in_reply_to: Array.isArray(thought.payload?.in_reply_to) ? thought.payload.in_reply_to.map((id) => ids[String(id)]) : [],
        ...(thought.kind === 'reflection' ? { actual_summary: frame.state.last_summary } : {}) };
      this.emit({ type: 'agent_thought', payload: { id: ids[thought.local_id ?? `${index}`], ts: Date.now() / 1000,
        tick: decision_tick, agent: thought.agent, kind: thought.kind, text: thought.text, payload } });
      if (thought.kind === 'plan' && frame.plan) this.emit({ type: 'tick_plan', payload: { ...frame.plan, state_version: this.version } });
    }, index * 450));
    if (!frame.thoughts.length) this.snapshot(frame);
  }
  start() {
    this.snapshot(frames[0]);
    this.continue_playback();
  }
  private continue_playback() {
    const branch = ['power_edit', 'partial'].includes(this.current.label);
    const pending = frames.filter((frame) => frame.state.tick > this.current.state.tick
      && (branch ? ['partial', 'recovered'].includes(frame.label) : frame.label === 'normal'));
    pending.forEach((frame, index) => this.schedule(() => this.playback(frame),
      C.time.real_seconds_per_tick * 500 + index * 3200));
  }
  control(cmd: string, value?: number) {
    if (cmd === 'pause') { this.stop(); this.paused = true; }
    else if (cmd === 'resume') { if (this.paused) { this.paused = false; this.continue_playback(); } }
    else if (cmd === 'speed' && value && value > 0) { this.stop(); this.speed = value; if (!this.paused) this.continue_playback(); }
    else if (cmd !== 'speed') throw new Error('未知控制命令');
    this.snapshot(this.current);
  }
  edit(values: Record<string, number>) {
    if (Object.keys(values).length === 1 && values.power === 300) {
      this.stop(); this.paused = false;
      const edit = frames.find((frame) => frame.label === 'power_edit');
      if (edit) this.snapshot(edit);
      frames.filter((frame) => frame.label === 'partial' || frame.label === 'recovered').forEach((frame, index) =>
        this.schedule(() => this.playback(frame), index * 3200));
    } else if (Object.keys(values).length === 1 && values.oxygen === 0 && frames.some((frame) => frame.label === 'failure')) {
      this.stop();
      const failure = frames.find((frame) => frame.label === 'failure')!;
      this.emit({ type: 'mission_failed', payload: { tick: failure.state.tick, reason: failure.state.failure_reason } });
      this.snapshot(failure);
    } else throw new Error('獨立展示只重播「電力 300」與「氧氣 0」；任意修改請切換連線模式。');
  }
  reset() { this.stop(); this.paused = false; this.speed = 1; this.start(); }
}
export function connect_mock(emit: (envelope: Envelope) => void): () => void {
  active?.stop(); active = new MockReplay(emit); active.start();
  return () => { active?.stop(); active = null; };
}
export async function mock_control(cmd: string, value?: number) { active?.control(cmd, value); }
export async function mock_edit(values: Record<string, number>) { active?.edit(values); }
export async function mock_reset() { active?.reset(); }
