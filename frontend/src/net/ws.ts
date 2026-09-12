import type { AgentThought, TickPlan, WorldEvent, WorldState } from '../../../shared/types';
import { useGameStore } from '../store/gameStore';
import { API_ROOT, get_world, is_mock } from './rest';
import { connect_mock, type Envelope } from './mockServer';

function accept(envelope: Envelope) {
  const store = useGameStore.getState();
  if (envelope.type === 'state_update') store.apply_state_update(envelope.payload as WorldState);
  else if (envelope.type === 'agent_thought') store.append_thought(envelope.payload as AgentThought);
  else if (envelope.type === 'tick_plan') store.append_plan(envelope.payload as TickPlan);
  else if (envelope.type === 'world_event') store.append_event(envelope.payload as WorldEvent);
  // mission_failed is notification only. The following authoritative snapshot
  // supplies crew death/resource state; no local resource or death arithmetic.
}

export function connect_world(): () => void {
  let closed = false;
  let socket: WebSocket | null = null;
  let retry: ReturnType<typeof setTimeout> | null = null;
  const store = useGameStore.getState();
  store.clear_session();
  store.set_mode(is_mock() ? 'mock' : 'live');
  if (is_mock()) { store.set_connection('connected'); return connect_mock(accept); }
  function connect() {
    if (closed) return;
    useGameStore.getState().set_connection('connecting');
    socket = new WebSocket(API_ROOT.replace(/^http/, 'ws') + '/ws');
    socket.onopen = () => {
      useGameStore.getState().set_connection('connected');
      get_world().then((world) => { if (!closed) useGameStore.getState().apply_state_update(world); }).catch(() => {});
    };
    socket.onmessage = (event) => {
      try { accept(JSON.parse(event.data) as Envelope); }
      catch { useGameStore.getState().set_error('無法讀取伺服器訊息'); }
    };
    socket.onclose = () => {
      if (closed) return;
      useGameStore.getState().set_connection('disconnected');
      retry = setTimeout(connect, 1500);
    };
    socket.onerror = () => socket?.close();
  }
  connect();
  return () => { closed = true; if (retry) clearTimeout(retry); socket?.close(); };
}
