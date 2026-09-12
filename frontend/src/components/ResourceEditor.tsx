import { useEffect, useState } from 'react';
import { X, SlidersHorizontal } from 'lucide-react';
import { useGameStore } from '../store/gameStore';
import { edit_resources } from '../net/rest';
import { resourceNames, formatNumber } from '../overlay/describe';

export default function ResourceEditor({ onClose }: { onClose: () => void }) {
  const world = useGameStore((state) => state.world);
  const [values, setValues] = useState<Record<string, string>>(() => Object.fromEntries(Object.entries(world?.resources ?? {}).map(([key, resource]) => [key, String(resource.value)])));
  const [dirty, setDirty] = useState<string[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => { const close = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose(); }; window.addEventListener('keydown', close); return () => window.removeEventListener('keydown', close); }, [onClose]);
  if (!world) return null;
  const submit = async (event: React.FormEvent) => {
    event.preventDefault(); setError('');
    const payload = Object.fromEntries(dirty.map((key) => [key, Number(values[key])]));
    if (dirty.some((key) => values[key].trim() === '' || !Number.isFinite(payload[key]))) { setError('請輸入有效數字'); return; }
    setBusy(true);
    try { await edit_resources(payload); onClose(); } catch (cause) { setError(cause instanceof Error ? cause.message : '資源修改失敗'); } finally { setBusy(false); }
  };
  return <div className="editor-backdrop" onPointerDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <form className="resource-editor panel-surface" onSubmit={(event) => void submit(event)} role="dialog" aria-modal="true" aria-label="修改公共資源">
      <div className="panel-heading"><span><SlidersHorizontal size={16} /> 修改公共資源</span><button type="button" className="icon-button" onClick={onClose} aria-label="關閉資源編輯"><X size={17} /></button></div>
      <p className="muted">改變基地庫存，觀察 Agent 如何重新協商。</p>
      {Object.entries(world.resources).map(([key, resource]) => <label className={`resource-field resource-${key}`} key={key}><span>{resourceNames[key]}<small>上限 {formatNumber(resource.capacity)} {resource.unit}</small></span><div><input aria-label={({ water: '水', oxygen: '氧氣', food: '食物', power: '電力' } as Record<string, string>)[key]} data-resource={key} type="number" step="any" value={values[key] ?? ''} onChange={(event) => { setValues({ ...values, [key]: event.target.value }); setDirty((current) => current.includes(key) ? current : [...current, key]); }} /><em>{resource.unit}</em></div></label>)}
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="editor-footer"><span>氧氣歸零將立即結束任務</span><button type="submit" className="primary-button" disabled={busy || dirty.length === 0}>{busy ? '套用中…' : '套用'}</button></div>
    </form>
  </div>;
}
