import { create } from 'zustand';
import type { AgentThought, TickPlan, WorldEvent, WorldState } from '../../../shared/types';

export type Target = { kind: 'crew' | 'plot' | 'object'; id: string };
export type Point = { x: number; y: number };
export interface GameStore {
  world: WorldState | null;
  thoughts: AgentThought[]; plans: TickPlan[]; events: WorldEvent[]; history: WorldState[];
  selected: Target | null; hover: (Target & Point) | null;
  camera: Point & { zoom: number }; anchors: Record<string, Point>;
  connection: 'connecting' | 'connected' | 'disconnected'; mode: 'mock' | 'live';
  error: string | null;
  apply_state_update: (state: WorldState) => void;
  append_thought: (thought: AgentThought) => void;
  append_plan: (plan: TickPlan) => void;
  append_event: (event: WorldEvent) => void;
  set_selected: (target: Target | null) => void;
  set_hover: (target: (Target & Point) | null) => void;
  set_camera: (camera: Partial<Point & { zoom: number }>) => void;
  set_anchors: (anchors: Record<string, Point>) => void;
  set_connection: (connection: GameStore['connection']) => void;
  set_mode: (mode: GameStore['mode']) => void;
  set_error: (error: string | null) => void;
  clear_session: () => void;
}

export const useGameStore = create<GameStore>((set) => ({
  world: null, thoughts: [], plans: [], events: [], history: [], selected: null, hover: null,
  camera: { x: 0, y: 0, zoom: 1 }, anchors: {}, connection: 'connecting', mode: 'live', error: null,
  apply_state_update: (state) => set((current) => {
    if (current.world && state.version <= current.world.version) return current;
    const reset = current.world && state.tick < current.world.tick;
    const history = reset ? [] : current.history.filter((item) => item.tick !== state.tick);
    return { world: state, history: [...history, state].slice(-24),
      ...(reset ? { thoughts: [], plans: [], events: [], selected: null, hover: null } : {}) };
  }),
  append_thought: (thought) => set((state) => state.thoughts.some((item) => item.id === thought.id)
    ? state : { thoughts: [...state.thoughts, thought].slice(-500) }),
  append_plan: (plan) => set((state) => state.plans.some((item) => item.tick === plan.tick && item.state_version === plan.state_version)
    ? state : { plans: [...state.plans, plan].slice(-100) }),
  append_event: (event) => set((state) => state.events.some((item) => item.id === event.id)
    ? state : { events: [...state.events, event].slice(-500) }),
  set_selected: (selected) => set({ selected }), set_hover: (hover) => set({ hover }),
  set_camera: (camera) => set((state) => ({ camera: { ...state.camera, ...camera } })),
  set_anchors: (anchors) => set({ anchors }), set_connection: (connection) => set({ connection }),
  set_mode: (mode) => set({ mode }), set_error: (error) => set({ error }),
  clear_session: () => set({ world: null, thoughts: [], plans: [], events: [], history: [], selected: null, hover: null, error: null }),
}));
