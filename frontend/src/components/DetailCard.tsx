import { useEffect } from 'react';
import { X } from 'lucide-react';
import { LineChart, Line, ResponsiveContainer, XAxis, YAxis, Tooltip as ChartTooltip } from 'recharts';
import { useGameStore } from '../store/gameStore';
import { describe, taskNames } from '../overlay/describe';

export default function DetailCard() {
  const world = useGameStore((state) => state.world);
  const selected = useGameStore((state) => state.selected);
  const history = useGameStore((state) => state.history);
  const close = useGameStore((state) => state.set_selected);
  useEffect(() => { const handler = (event: KeyboardEvent) => { if (event.key === 'Escape') close(null); }; window.addEventListener('keydown', handler); return () => window.removeEventListener('keydown', handler); }, [close]);
  if (!world || !selected) return null;
  const data = describe(world, selected);
  const recentTasks = selected.kind === 'crew' ? history.map((snapshot) => ({ tick: snapshot.tick, task: snapshot.crew[selected.id]?.current_task }))
    .filter((item, index, items) => item.task && (index === 0 || item.task !== items[index - 1].task)).slice(-3).reverse() : [];
  const points = history.map((snapshot) => ({ tick: snapshot.tick,
    value: selected.kind === 'crew' ? snapshot.crew[selected.id]?.food_energy
      : selected.kind === 'plot' ? snapshot.plots.find((plot) => plot.id === selected.id)?.progress_ticks
      : snapshot.resources[selected.id as keyof typeof snapshot.resources]?.value })).filter((point) => point.value != null);
  return <section className={`detail-card panel-surface ${data.warning ? 'is-warning' : ''}`} aria-label="物件詳細資訊"><div className="panel-heading"><span>{data.title}</span><button className="icon-button" aria-label="關閉詳細卡" onClick={() => close(null)}><X size={16} /></button></div><small className="muted">{data.subtitle}</small><div className="detail-lines">{data.lines.map((line) => <p key={line}>{line}</p>)}</div>
    {recentTasks.length > 0 && <div className="detail-lines"><small className="muted">最近動作</small>{recentTasks.map((item) => <p key={item.tick}>TICK {item.tick} · {taskNames[item.task!] ?? item.task}</p>)}</div>}
    {points.length > 0 && <><div className="chart-label">近期變化<span>{selected.kind === 'crew' ? '個人能量 · kcal' : selected.kind === 'plot' ? '有效生長 ticks' : world.resources[selected.id as keyof typeof world.resources]?.unit}</span></div><div className="detail-chart"><ResponsiveContainer width="100%" height="100%"><LineChart data={points}><XAxis dataKey="tick" hide /><YAxis hide domain={['auto', 'auto']} /><ChartTooltip contentStyle={{ background: '#19221f', border: '1px solid #546055', borderRadius: 6, fontSize: 11 }} labelFormatter={(tick) => `TICK ${tick}`} /><Line dataKey="value" stroke="#b7c69b" strokeWidth={2} dot={false} isAnimationActive={false} /></LineChart></ResponsiveContainer></div></>}
  </section>;
}
