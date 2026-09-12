// Read-only recorded replay; no control requests or provider calls.
import assert from 'node:assert/strict';
import { chromium } from '../frontend/node_modules/playwright-core/index.mjs';

const history = await (await fetch('http://127.0.0.1:8001/history?limit=1000')).json();
const thoughts = history.filter(e => e.type === 'agent_thought' && e.payload.agent === 'human'
  && e.payload.payload?.world_version === 30).map(e => e.payload);
assert.equal(thoughts.length, 2, 'Requires the two recorded Human replies at version 30');
const browser = await chromium.launch({ executablePath: '/opt/google/chrome/chrome', headless: true, args: ['--no-sandbox'] });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('http://127.0.0.1:5175');
  const checks = await page.evaluate(async recorded => {
    const { publicText } = await import('/src/overlay/publicText.ts');
    const { useGameStore } = await import('/src/store/gameStore.ts');
    useGameStore.setState({ thoughts: recorded });
    const sample = recorded[0];
    return {
      actual: publicText(sample),
      nullPayload: publicText({ ...sample, payload: null }),
      blank: publicText({ ...sample, payload: { explanation: { decision_reason: ' ' } } }),
      invalid: publicText({ ...sample, payload: { explanation: { decision_reason: ['not text'] } } }),
      core: publicText({ ...sample, agent: 'core' }),
    };
  }, thoughts);
  assert.equal(checks.actual, thoughts[0].payload.explanation.decision_reason.trim());
  for (const key of ['nullPayload', 'blank', 'invalid', 'core']) assert.equal(checks[key], thoughts[0].text);
  await page.getByRole('button', { name: 'Agent 對話', exact: true }).click();
  const rendered = await page.locator('.from-human .chat-content > p').allTextContents();
  assert.deepEqual(rendered, thoughts.map(t => t.payload.explanation.decision_reason.trim()));
  assert.notEqual(rendered[0], rendered[1]);
  const originals = page.locator('.from-human details').filter({ has: page.locator('summary', { hasText: '查看原始狀態摘要' }) });
  await originals.first().locator('summary').click();
  assert.equal(await originals.first().locator('p').innerText(), thoughts[0].text);
  await page.screenshot({ path: 'artifacts/human-public-main-text.png' });
  assert.deepEqual(errors, []);
  console.log('PASS: distinct recorded Human answers, original summaries, safe fallbacks; no paid calls');
} finally {
  await browser.close();
}
