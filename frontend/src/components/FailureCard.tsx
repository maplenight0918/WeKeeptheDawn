import { useState } from 'react';
import { AlertTriangle, RotateCcw } from 'lucide-react';
import { useGameStore } from '../store/gameStore';
import { reset_world } from '../net/rest';

export default function FailureCard() {
  const world = useGameStore((state) => state.world);
  const [error, setError] = useState('');
  if (!world?.failed) return null;
  const restart = async () => { try { await reset_world(); } catch (cause) { setError(cause instanceof Error ? cause.message : '無法重新開始'); } };
  return <section className="failure-card panel-surface" role="alert"><div className="failure-icon"><AlertTriangle size={22} /></div><small>MISSION ENDED · TICK {world.tick}</small><h1>與基地失去聯繫</h1><p>{world.failure_reason ?? 'Crew 生存條件已無法維持。'}</p><span className="failure-note">世界已停止。你可以回看 Agent 對話與最後的決策。</span>{error && <p className="form-error">{error}</p>}<button className="primary-button" onClick={() => void restart()}><RotateCcw size={14} />重新開始</button></section>;
}
