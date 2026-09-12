import type { ResourceKey, WorldState } from '../../../shared/types';
import { useGameStore } from '../store/gameStore';
import { mock_control, mock_edit, mock_reset } from './mockServer';

export const API_ROOT = (import.meta.env.VITE_API_URL || 'http://127.0.0.1:8001').replace(/\/$/, '');
export function is_mock() { return new URLSearchParams(window.location.search).get('mock') === '1'; }
async function request(path: string, body?: unknown): Promise<WorldState> {
  const response = await fetch(`${API_ROOT}${path}`, { method: body === undefined ? 'GET' : 'POST',
    headers: { 'Content-Type': 'application/json' }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  if (!response.ok) throw new Error(`API ${response.status}: ${await response.text()}`);
  return response.json();
}
export async function get_world() { return request('/world'); }
async function action(run: () => Promise<void | WorldState>) {
  try {
    const result = await run();
    if (result) useGameStore.getState().apply_state_update(result);
    useGameStore.getState().set_error(null);
  } catch (error) {
    useGameStore.getState().set_error(error instanceof Error ? error.message : String(error));
    throw error;
  }
}
export async function control(cmd: 'pause' | 'resume' | 'speed', value?: number) {
  return action(() => is_mock() ? mock_control(cmd, value) : request('/control', { cmd, value }));
}
export async function edit_resources(values: Partial<Record<ResourceKey, number>>) {
  return action(() => is_mock() ? mock_edit(values as Record<string, number>) : request('/resources', values));
}
export async function reset_world() { return action(() => is_mock() ? mock_reset() : request('/world/reset', {})); }
