import { useGameStore } from '../store/gameStore';
import { describe } from '../overlay/describe';

export default function Tooltip() {
  const world = useGameStore((state) => state.world);
  const hover = useGameStore((state) => state.hover);
  if (!world || !hover) return null;
  const data = describe(world, hover);
  return <div className={`world-tooltip panel-surface ${data.warning ? 'is-warning' : ''}`} role="tooltip" style={{ left: Math.min(window.innerWidth - 270, hover.x + 18), top: Math.min(window.innerHeight - 165, hover.y + 18) }}><small>{data.subtitle}</small><strong>{data.title}</strong>{data.lines.map((line) => <span key={line}>{line}</span>)}</div>;
}
