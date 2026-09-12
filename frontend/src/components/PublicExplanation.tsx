import { payloadOf } from '../overlay/bridge';

const strings = (value: unknown): string[] => Array.isArray(value)
  ? value.filter((item): item is string => typeof item === 'string' && item.trim().length > 0) : [];
const text = (value: unknown) => typeof value === 'string' ? value : '';

export default function PublicExplanation({ value }: { value: unknown }) {
  const explanation = payloadOf(value);
  const sections: [string, string[]][] = [
    ['觀察', strings(explanation.observations)],
    ['公開分析', strings([explanation.decision_reason])],
    ['衝突', strings(explanation.conflicts)],
    ['追問原因', strings([explanation.follow_up_reason])],
    ['不確定性', strings(explanation.uncertainties)],
  ];
  const proposals = (Array.isArray(explanation.proposals) ? explanation.proposals : []).map(payloadOf);
  const reviews = (Array.isArray(explanation.reviews) ? explanation.reviews : []).map(payloadOf);
  if (!sections.some(([, items]) => items.length) && !proposals.length && !reviews.length) return null;
  const dispositions: Record<string, string> = { accept: '接受', modify: '調整', reject: '不採用', needs_clarification: '待釐清' };
  return <details className="public-explanation">
    <summary>公開分析與評估 · {proposals.length} 項新提案／{reviews.length} 項評估</summary>
    <p className="explanation-note">公開理由摘要，非內部思考或執行結果；沒有新提案不代表沒有分析。</p>
    {sections.filter(([, items]) => items.length).map(([label, items]) => <section key={label}>
      <h4>{label}</h4>{items.map((item, index) => <p key={index}>{item}</p>)}
    </section>)}
    {proposals.map((proposal, index) => <section key={index}>
      <h4>提案：{text(proposal.strategy)}</h4>
      <p>{text(proposal.reason)}</p><p>{text(proposal.expected_effect)}</p>
      {strings(proposal.tradeoffs).map((item, i) => <p key={`tradeoff-${i}`}>取捨：{item}</p>)}
      {strings(proposal.evidence).map((item, i) => <p key={`evidence-${i}`}>依據：{item}</p>)}
      <small>提案 ID：{text(proposal.proposal_id)}</small>
    </section>)}
    {reviews.map((review, index) => <section key={index}>
      <h4>提案評估 · {dispositions[text(review.disposition)] ?? text(review.disposition)}</h4>
      <p>{text(review.assessment)}</p>
      <small>訊息：{text(review.message_id)}／提案：{text(review.proposal_id)}</small>
    </section>)}
  </details>;
}
