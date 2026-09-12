import { useEffect, useRef, useState } from 'react';
import type { AgentThought } from '../../../shared/types';
import { useGameStore } from '../store/gameStore';
import { useAnchors, conversationId } from '../overlay/bridge';
import AgentAvatar, { agentNames } from './AgentAvatar';
import { formatNumber } from '../overlay/describe';
import { publicText } from '../overlay/publicText';

function ResourceFloats() {
  const world = useGameStore((state) => state.world);
  const frozen = Boolean(world?.paused || world?.failed);
  const speed = world?.speed ?? 1;
  const anchors = useAnchors();
  const previous = useRef(world);
  const frozen_since = useRef<number | null>(null);
  const [floats, setFloats] = useState<{ id: string; key: string; text: string; positive: boolean; born: number }[]>([]);
  useEffect(() => {
    const before = previous.current;
    previous.current = world;
    if (!world || !before || world.tick < before.tick) { setFloats([]); return; }
    const changes = Object.entries(world.resources).flatMap(([key, resource]) => {
      const old = before.resources[key as keyof typeof before.resources];
      const delta = resource.value - old.value;
      return delta === 0 ? [] : [{ id: `${world.version}-${key}`, key,
        text: `${delta > 0 ? '+' : '−'}${formatNumber(Math.abs(delta))} ${resource.unit}`, positive: delta > 0, born: Date.now() }];
    });
    if (changes.length) setFloats((current) => [...current, ...changes].slice(-16));
  }, [world]);
  useEffect(() => {
    if (frozen) { frozen_since.current ??= Date.now(); return; }
    if (frozen_since.current !== null) {
      const stopped_for = Date.now() - frozen_since.current;
      frozen_since.current = null;
      setFloats((current) => current.map((item) => ({ ...item, born: item.born + stopped_for })));
    }
    const timer = window.setInterval(() => setFloats((current) => current.filter((item) => Date.now() - item.born < 1500)), 250);
    return () => window.clearInterval(timer);
  }, [frozen]);
  return <>{floats.map((item) => { const anchor = anchors[item.key]; return anchor ? <span key={item.id} className={`resource-float ${item.positive ? 'gain' : 'loss'}`} style={{ left: anchor.x, top: anchor.y, animationDuration: `${1500 / speed}ms` }}>{item.text}</span> : null; })}</>;
}

export default function Bubble() {
  const thoughts = useGameStore((state) => state.thoughts);
  const world = useGameStore((state) => state.world);
  const frozen = Boolean(world?.paused || world?.failed);
  const speed = world?.speed ?? 1;
  const intervention = useGameStore((state) => state.events.filter((event) => event.type === 'player_edit').slice(-1)[0]?.id);
  const anchors = useAnchors();
  const queue = useRef<AgentThought[]>([]);
  const seen = useRef(new Set<string>());
  const active = useRef<AgentThought | null>(null);
  const [current, setCurrent] = useState<AgentThought | null>(null);
  const [letters, setLetters] = useState(0);
  useEffect(() => { if (intervention) { queue.current = []; active.current = null; setCurrent(null); } }, [intervention]);
  useEffect(() => {
    if (thoughts.length === 0) { queue.current = []; seen.current.clear(); active.current = null; setCurrent(null); return; }
    for (const thought of thoughts) if (!seen.current.has(thought.id)) { seen.current.add(thought.id); queue.current.push(thought); }
    // Display complete conversational turns; full history remains in the drawer.
    const rounds = [...new Set(queue.current.map(conversationId))];
    if (rounds.length > 3) {
      const keep = new Set([active.current ? conversationId(active.current) : rounds[0], ...rounds.slice(-2)]);
      queue.current = queue.current.filter((thought) => keep.has(conversationId(thought)));
    }
    if (!active.current && queue.current.length) { active.current = queue.current.shift()!; setCurrent(active.current); }
  }, [thoughts]);
  useEffect(() => { if (current) setLetters(0); }, [current?.id]);
  useEffect(() => {
    if (!current || frozen) return;
    const typewriter = window.setInterval(() => setLetters((count) => count + 2), 24 / speed);
    const next = window.setTimeout(() => { active.current = queue.current.shift() ?? null; setCurrent(active.current); }, 4600 / speed);
    return () => { window.clearInterval(typewriter); window.clearTimeout(next); };
  }, [current?.id, frozen, speed]);
  if (!current) return <ResourceFloats />;
  const anchor = anchors[current.agent] ?? { x: window.innerWidth / 2, y: window.innerHeight / 2 };
  const text = publicText(current);
  const x = Math.min(window.innerWidth - 156, Math.max(156, anchor.x));
  const y = Math.min(window.innerHeight - 100, Math.max(180, anchor.y));
  return <><ResourceFloats /><div className={`world-bubble bubble-${current.agent} kind-${current.kind}`} key={current.id} style={{ left: x, top: y, animationDuration: `${4600 / speed}ms` }} aria-live="polite"><div className="bubble-byline"><AgentAvatar agent={current.agent} /><strong>{agentNames[current.agent]}</strong><span>{current.kind === 'plan' ? '執行計畫' : current.kind === 'reflection' ? '結果回報' : '協商中'}<i className="typing-dot" /></span></div><p>{text.slice(0, letters)}<span className="typing-caret">▏</span></p></div></>;
}
