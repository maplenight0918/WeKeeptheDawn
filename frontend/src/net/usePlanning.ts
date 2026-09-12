import { useEffect, useState } from 'react';
import { useGameStore } from '../store/gameStore';
import { API_ROOT } from './rest';

// Observe the backend's version-bound decision request. This is not a claim
// that a provider is online: an external world also waits when its bridge is offline.
export function usePlanning() {
  const world = useGameStore((state) => state.world);
  const connection = useGameStore((state) => state.connection);
  const mode = useGameStore((state) => state.mode);
  const tick = world?.tick, version = world?.version;
  const enabled = mode === 'live' && connection === 'connected' && !!world
    && !world.paused && !world.paused_reason && !world.failed;
  const [observed, setObserved] = useState<{ tick: number; version: number } | null>(null);

  useEffect(() => {
    setObserved(null);
    if (!enabled) return;
    let closed = false;
    let next: ReturnType<typeof setTimeout>;
    let controller: AbortController | undefined;
    async function poll() {
      controller = new AbortController();
      const timeout = setTimeout(() => controller?.abort(), 3000);
      try {
        const response = await fetch(`${API_ROOT}/decision`, { signal: controller.signal });
        if (!response.ok) throw new Error('Decision status unavailable');
        const request = await response.json();
        if (!closed) setObserved(request?.status === 'awaiting' && request.tick === tick
          && request.state_version === version ? { tick: request.tick, version: request.state_version } : null);
      } catch {
        if (!closed) setObserved(null);
      } finally {
        clearTimeout(timeout);
        if (!closed) next = setTimeout(poll, 500);
      }
    }
    void poll();
    return () => { closed = true; clearTimeout(next); controller?.abort(); };
  }, [enabled, tick, version]);

  return enabled && observed?.tick === tick && observed?.version === version;
}
