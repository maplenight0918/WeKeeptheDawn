import { useGameStore } from '../store/gameStore';

export interface ScreenPoint { x: number; y: number }
export function useAnchors(): Record<string, ScreenPoint> {
  return useGameStore((state) => state.anchors);
}

export function payloadOf(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown> : {};
}

export function conversationId(thought: { tick: number; payload?: unknown }): string {
  return String(payloadOf(thought.payload).conversation_id ?? `decision-${thought.tick}`);
}
