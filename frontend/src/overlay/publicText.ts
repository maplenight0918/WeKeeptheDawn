import type { AgentThought } from '../../../shared/types';

/** Prefer Human's supplied public answer, never private content or invented prose. */
export function publicText(thought: AgentThought): string {
  const payload = thought.payload;
  const explanation = payload && typeof payload === 'object' && !Array.isArray(payload)
    ? (payload as Record<string, unknown>).explanation : undefined;
  const reason = explanation && typeof explanation === 'object' && !Array.isArray(explanation)
    ? (explanation as Record<string, unknown>).decision_reason : undefined;
  if (thought.agent === 'human' && typeof reason === 'string' && reason.trim()) return reason.trim();
  return thought.text.replace(/^\[MOCK\]\s*/, '');
}
