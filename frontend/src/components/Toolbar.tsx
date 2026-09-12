import { useState } from 'react';
import { Pause, Play, RotateCcw, SlidersHorizontal } from 'lucide-react';
import { control, reset_world } from '../net/rest';
import { useGameStore } from '../store/gameStore';
import ResourceEditor from './ResourceEditor';

export default function Toolbar() {
  const world = useGameStore((state) => state.world);
  const connection = useGameStore((state) => state.connection);
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const act = async (action: () => Promise<unknown>) => { setBusy(true); setError(''); try { await action(); } catch (cause) { setError(cause instanceof Error ? cause.message : '操作失敗'); } finally { setBusy(false); } };
  const disabled = busy || connection !== 'connected' || !world;
  return <>
    <nav className="toolbar panel-surface" aria-label="世界控制">
      {error && <div className="toolbar-error" role="alert">{error}</div>}
      <button className="transport-button" aria-label={world?.paused ? '繼續' : '暫停'} disabled={disabled || world?.failed} onClick={() => void act(() => control(world?.paused ? 'resume' : 'pause'))}>{world?.paused ? <Play size={17} fill="currentColor" /> : <Pause size={17} fill="currentColor" />}</button>
      <span className="toolbar-divider" />
      <div className="speed-options" aria-label="時間速度">{[1, 5, 20].map((speed) => <button key={speed} className={world?.speed === speed ? 'active' : ''} disabled={disabled} onClick={() => void act(() => control('speed', speed))}>×{speed}</button>)}</div>
      <span className="toolbar-divider" />
      <button className="resource-button" disabled={disabled} onClick={() => setEditing(true)}><SlidersHorizontal size={15} /><span>修改資源</span></button>
      <button className="restart-button" aria-label="重新開始" title="重新開始" disabled={disabled} onClick={() => void act(reset_world)}><RotateCcw size={15} /></button>
    </nav>
    {editing && <ResourceEditor onClose={() => setEditing(false)} />}
  </>;
}
