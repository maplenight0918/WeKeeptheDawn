import { useEffect, useRef, useState } from 'react';
import { ChevronDown, ChevronUp, MessageCircle, ArrowRight } from 'lucide-react';
import type { AgentThought } from '../../../shared/types';
import { useGameStore } from '../store/gameStore';
import { conversationId, payloadOf } from '../overlay/bridge';
import { formatNumber } from '../overlay/describe';
import AgentAvatar, { agentNames } from './AgentAvatar';
import PublicExplanation from './PublicExplanation';
import { publicText } from '../overlay/publicText';

export default function AgentDrawer() {
  const thoughts = useGameStore((state) => state.thoughts);
  const plans = useGameStore((state) => state.plans);
  const mode = useGameStore((state) => state.mode);
  const clearHover = useGameStore((state) => state.set_hover);
  const [open, setOpen] = useState(false);
  const [full, setFull] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { if (open) end.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); }, [thoughts.length, open]);
  const grouped = new Map<string, AgentThought[]>();
  for (const thought of thoughts) { const key = conversationId(thought); grouped.set(key, [...(grouped.get(key) ?? []), thought]); }
  const rounds = [...grouped.entries()].slice(full ? -30 : -3);
  const latest = thoughts[thoughts.length - 1];
  const last = latest ? { ...latest, text: publicText(latest) } : undefined;
  return <aside className={`agent-drawer panel-surface ${open ? 'is-open' : ''} ${full ? 'show-full' : ''}`} aria-label="Agent 對話" onPointerEnter={() => clearHover(null)}>
    <button className="drawer-toggle" aria-label="Agent 對話" aria-expanded={open} onClick={() => setOpen(!open)}><span className="comms-icon"><MessageCircle size={18} /><i /></span><span><strong>AGENT COMMS</strong><small>{open ? 'Core · Plant · Human 協商對話' : last ? `${agentNames[last.agent]} · ${last.text.replace(/^\[MOCK\]\s*/, '').slice(0, 28)}` : '等待基地連線…'}</small></span><span className="message-count">{thoughts.length}</span>{open ? <ChevronDown size={16} /> : <ChevronUp size={16} />}</button>
    {open && <><div className="drawer-subhead"><span>{mode === 'mock' ? '● MOCK · 預錄展示' : '● LIVE · 外部 Agent'}</span><button onClick={() => setFull(!full)}>{full ? '精簡' : '完整'}對話</button></div><div className="conversation-scroll">
      {rounds.length === 0 && <div className="conversation-empty"><MessageCircle size={25} /><p>等待第一輪協商</p><small>建議、計畫與結算結果會留在這裡。</small></div>}
      {rounds.map(([round, messages]) => <section className="conversation-round" key={round}><div className="round-label"><span />決策回合 · TICK {messages[0].tick}<span /></div>
        {messages.map((thought) => {
          const payload = payloadOf(thought.payload);
          const reply = thoughts.find((item) => item.id === payload.reply_to);
          const plan = plans.find((item) => item.tick === thought.tick
            && item.state_version === payload.world_version);
          const summary = payloadOf(payload.actual_summary);
          const generation = payloadOf(summary.generation), irrigation = payloadOf(summary.irrigation), water = payloadOf(summary.water_plant);
          return <article key={thought.id} className={`chat-message kind-${thought.kind} from-${thought.agent}`}>
            <AgentAvatar agent={thought.agent} /><div className="chat-content"><div className="chat-byline"><strong>{payload.source === 'bridge_result' ? 'Bridge 結算回報' : agentNames[thought.agent]}</strong><ArrowRight size={10} /><span>{String(payload.to ?? (thought.agent === 'core' ? '全體' : 'Core')).replace('all', '全體')}</span><small>{payload.mock === true ? 'MOCK · ' : ''}{thought.kind === 'plan' ? '提交計畫' : thought.kind === 'reflection' ? '結果反思' : thought.kind === 'risk' ? '風險' : thought.kind === 'validation_error' ? '驗證錯誤' : ''}</small></div>
              {reply && <div className="reply-preview">↳ {agentNames[reply.agent]}：{publicText(reply).slice(0, 36)}</div>}
              <p>{publicText(thought)}</p>
              {thought.agent === 'human' && publicText(thought) !== thought.text.replace(/^\[MOCK\]\s*/, '') && <details className="public-explanation"><summary>查看原始狀態摘要</summary><p>{thought.text.replace(/^\[MOCK\]\s*/, '')}</p></details>}
              <small className="message-context">第 {String(payload.round ?? '—')} 輪 · 世界版本 {String(payload.world_version ?? '—')}</small>
              <PublicExplanation value={payload.explanation} />
              {thought.kind === 'plan' && plan && <div className="plan-facts"><span>灌溉 <b>{plan.irrigation.length} 塊</b></span><span>發電 <b>{Object.values(plan.generation).filter((value) => value > 0).length} 人</b></span><span>製水 <b>{formatNumber(plan.water_production_l)} L</b></span></div>}
              {(thought.kind === 'reflection' || payload.status === 'confirmed') && payload.actual_summary != null && <div className="result-facts"><span>實際結算</span><b>+{formatNumber(Number(generation.power_out ?? 0))} EU</b><b>+{formatNumber(Number(water.actual ?? 0))} L</b><small>{Array.isArray(irrigation.succeeded) ? irrigation.succeeded.length : 0} 塊灌溉成功</small></div>}
              {payload.status === 'unconfirmed' && <small role="status">結果未確認，尚未收到可配對的結算證據。</small>}
            </div>
          </article>;
        })}
      </section>)}<div ref={end} />
    </div></>}
  </aside>;
}
