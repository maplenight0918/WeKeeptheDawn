import { Cpu, Leaf, Users } from 'lucide-react';

export const agentNames: Record<string, string> = { core: 'Core', plant: 'Plant', human: 'Human' };
export default function AgentAvatar({ agent }: { agent: string }) {
  const Icon = agent === 'plant' ? Leaf : agent === 'human' ? Users : Cpu;
  return <span className={`agent-avatar agent-${agent}`} aria-label={`${agentNames[agent] ?? agent} avatar`}>
    <Icon aria-hidden="true" focusable="false" size={15} strokeWidth={1.6} />
  </span>;
}
