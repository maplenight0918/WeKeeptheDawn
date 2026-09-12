import { chromium } from '../frontend/node_modules/playwright-core/index.mjs';
import { mkdir, writeFile } from 'node:fs/promises';

const root = process.env.FRONTEND_ROOT || 'http://127.0.0.1:5174';
const browser = await chromium.launch({
  ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}),
  headless: true,
  args: ['--no-sandbox', '--disable-dev-shm-usage', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
});
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const errors = [];
const checks = [];
page.on('pageerror', error => errors.push(error.message));
function check(name, condition) { if (!condition) throw new Error(name); checks.push(name); }
async function state() {
  return page.evaluate(async () => {
    const { useGameStore } = await import('/src/store/gameStore.ts');
    const store = useGameStore.getState();
    return { world: store.world, thoughts: store.thoughts, plans: store.plans };
  });
}
async function wait_world(predicate) {
  const handle = await page.waitForFunction((source) => {
    const world = window.__interaction_store__.getState().world;
    return new Function('world', `return (${source})(world)`)(world) ? world : false;
  }, String(predicate), { timeout: 20000 });
  return handle.jsonValue();
}
async function edit(label, value) {
  await page.getByRole('button', { name: '修改資源', exact: true }).click();
  await page.getByRole('dialog', { name: '修改公共資源' }).waitFor();
  await page.getByRole('spinbutton', { name: label, exact: true }).fill(String(value));
  await page.getByRole('button', { name: '套用', exact: true }).click();
  await page.getByRole('dialog', { name: '修改公共資源' }).waitFor({ state: 'hidden' });
}
await mkdir('artifacts', { recursive: true });
try {
  await page.goto(`${root}/?mock=1`, { waitUntil: 'networkidle' });
  await page.waitForFunction(() => window.__GREENHOUSE_DEBUG__?.ready, { timeout: 30000 });
  await page.evaluate(async () => { window.__interaction_store__ = (await import('/src/store/gameStore.ts')).useGameStore; });
  await page.evaluate(() => document.fonts.ready);
  const initial_positions = await page.evaluate(() => window.__GREENHOUSE_DEBUG__.crew_positions);
  await wait_world(world => world?.tick >= 2);
  const working_positions = await page.evaluate(() => window.__GREENHOUSE_DEBUG__.crew_positions);
  check('crew positions move along scene routes', !!initial_positions && !!working_positions
    && Object.entries(initial_positions).some(([key, position]) => {
      const next = working_positions[key];
      return next && (next.x !== position.x || next.y !== position.y);
    }));
  const targets = await page.evaluate(() => window.__GREENHOUSE_DEBUG__.targets);
  await page.mouse.click(targets.water.x, targets.water.y);
  const detail = page.getByRole('region', { name: '物件詳細資訊' });
  await detail.waitFor();
  check('resource detail card shows units and recent history', (await detail.innerText()).includes('L') && await detail.locator('.detail-chart').count() === 1);
  await page.keyboard.press('Escape');
  check('Escape closes detail card', await detail.count() === 0);

  await page.getByRole('button', { name: 'Agent 對話', exact: true }).click();
  await page.locator('.chat-message.kind-reflection .result-facts').first().waitFor();
  check('Core chat message rendered', await page.locator('.chat-message.from-core').count() > 0);
  check('Plant chat message rendered', await page.locator('.chat-message.from-plant').count() > 0);
  check('Human chat message rendered', await page.locator('.chat-message.from-human').count() > 0);
  const avatar_alignment = await page.locator('.chat-message .agent-avatar').evaluateAll((avatars) => avatars.map((avatar) => {
    const frame = avatar.getBoundingClientRect();
    const icon = avatar.querySelector('svg')?.getBoundingClientRect();
    return icon ? {
      agent: [...avatar.classList].find((name) => name.startsWith('agent-')),
      offset_x: Math.abs((frame.left + frame.width / 2) - (icon.left + icon.width / 2)),
      offset_y: Math.abs((frame.top + frame.height / 2) - (icon.top + icon.height / 2)),
    } : null;
  }));
  check('Core Plant Human avatar SVGs center in their frames', avatar_alignment.length >= 3
    && avatar_alignment.every((entry) => entry && entry.offset_x <= 0.5 && entry.offset_y <= 0.5));
  check('reply previews show conversation relationships', await page.locator('.reply-preview').count() > 0);
  check('plan card shows allocation facts', await page.locator('.kind-plan .plan-facts').count() > 0);
  check('reflection card shows actual recorded summary', await page.locator('.kind-reflection .result-facts').count() > 0);
  const initial = await state();
  const reflection = initial.thoughts.find(thought => thought.kind === 'reflection');
  const matching_plan = initial.plans.find(plan => plan.tick === reflection.tick);
  check('plan and reflection share the decision tick', !!matching_plan && reflection.payload.actual_summary.tick === matching_plan.tick + 1);
  await page.screenshot({ path: 'artifacts/mock-chat-interactions.png' });
  await page.getByRole('button', { name: 'Agent 對話', exact: true }).click();

  await edit('電力', 300);
  await wait_world(world => world?.resources.power.value === 300);
  check('power edit uses exact recorded intervention', (await state()).world.resources.power.value === 300);
  const partial = { world: await wait_world(world => world?.plots.filter(plot => plot.consecutive_unirrigated_ticks === 1).length === 8) };
  check('partial allocation irrigates twelve plots', partial.world.last_summary.irrigation.succeeded.length === 12);
  check('eight plots have one missed irrigation', partial.world.plots.filter(plot => plot.consecutive_unirrigated_ticks === 1).length === 8);
  await page.screenshot({ path: 'artifacts/mock-partial-irrigation.png' });
  const critical = await wait_world(world => world?.plots.filter(plot => plot.consecutive_unirrigated_ticks === 2).length === 8);
  check('second recorded shortage increases interruption count', critical.plots.filter(plot => plot.consecutive_unirrigated_ticks === 2).length === 8);
  const recovered = await wait_world(world => world?.tick >= 5 && world.plots.every(plot => plot.irrigated_last_tick && plot.consecutive_unirrigated_ticks === 0));
  check('recovery supplies all twenty plots', recovered.last_summary.irrigation.succeeded.length === 20);
  await page.screenshot({ path: 'artifacts/mock-recovered.png' });

  await edit('氧氣', 0);
  await page.locator('.failure-card').waitFor();
  const failed = await state();
  check('oxygen zero shows failure and all crew dead', failed.world.failed && Object.values(failed.world.crew).every(crew => !crew.alive));
  check('world remains visible behind failure card', await page.locator('canvas').isVisible());
  await page.screenshot({ path: 'artifacts/mock-failure.png' });
  await page.locator('.failure-card').getByRole('button', { name: '重新開始', exact: true }).click();
  await page.locator('.failure-card').waitFor({ state: 'hidden' });
  const reset = await state();
  check('reset restores living initial snapshot', reset.world.tick === 0 && !reset.world.failed && Object.values(reset.world.crew).every(crew => crew.alive));
  check('no browser runtime errors', errors.length === 0);
  const report = { passed: true, checks: checks.length, assertions: checks, errors };
  await writeFile('artifacts/frontend_interactions.json', JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
} finally {
  await browser.close();
}
