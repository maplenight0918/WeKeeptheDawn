import { Radio } from 'lucide-react';
import { C } from '../config';
import { useGameStore } from '../store/gameStore';
import { usePlanning } from '../net/usePlanning';

export default function MissionBadge() {
  const world = useGameStore((state) => state.world);
  const connection = useGameStore((state) => state.connection);
  const mode = useGameStore((state) => state.mode);
  const planning = usePlanning();
  const tick = world?.tick ?? 0;
  const hours = tick * C.time.simulation_hours_per_tick;
  const alive = world ? Object.values(world.crew).filter((crew) => crew.alive).length : C.crew.count;
  const stateLabel = connection !== 'connected' ? connection === 'connecting' ? '連線中' : '已離線' : world?.failed ? '任務終止' : world?.paused_reason === 'error' ? '錯誤暫停' : world?.paused ? '已暫停' : planning ? 'Agent 規劃中' : '運作中';
  return <header className="mission-badge panel-surface">
    <div className="mission-brand"><span className="brand-orbit">◎</span><div>SPACE GREENHOUSE<small>MARS HABITAT · 生存經營</small></div></div>
    <div className="mission-clock"><span>DAY {String(Math.floor(hours / C.time.hours_per_day) + 1).padStart(2, '0')}</span><strong>{String(hours % C.time.hours_per_day).padStart(2, '0')}:00</strong><span>TICK {tick.toLocaleString()}</span></div>
    <div className="mission-status"><span className={`status-dot ${connection !== 'connected' || world?.failed ? 'status-alert' : ''}`} />{stateLabel}<span>{alive} / {C.crew.count} 存活</span><i><Radio size={10} />{mode === 'mock' ? 'MOCK DEMO' : 'LIVE LINK'}</i></div>
    {planning && <p className="planning-status" role="status" title="後端正在等待有效計畫；此提示不保證模型或 bridge 已連線。">等待 Agent 計畫，世界時間與資源消耗暫停。</p>}
  </header>;
}
