import { chromium } from '../frontend/node_modules/playwright-core/index.mjs';
import { mkdir, writeFile } from 'node:fs/promises';

const root = process.env.FRONTEND_ROOT || 'http://127.0.0.1:5173';
const browser = await chromium.launch({
  ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}),
  headless: true,
  args: ['--no-sandbox', '--disable-dev-shm-usage', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
});
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const errors = [];
page.on('pageerror', error => errors.push(error.message));
await mkdir('artifacts', { recursive: true });
try {
  await page.goto(`${root}/?mock=1`, { waitUntil: 'networkidle' });
  await page.waitForFunction(() => window.__GREENHOUSE_DEBUG__?.ready, { timeout: 30000 });
  await page.evaluate(() => document.fonts.ready);
  const debug = await page.evaluate(() => window.__GREENHOUSE_DEBUG__);
  if (debug.plot_count !== 20) throw new Error(`Expected 20 rendered plots, got ${debug.plot_count}`);
  if (debug.plot_positions.length !== 20 || debug.plot_positions.some(({ x, y }) => x < 0 || x > 1440 || y < 0 || y > 900)) {
    throw new Error('All 20 plots must be inside the initial viewport');
  }
  for (const key of ['water', 'oxygen', 'food', 'power']) {
    if (!debug.targets[key]) throw new Error(`Missing rendered target: ${key}`);
    const { x, y } = debug.targets[key];
    if (x < 0 || x > 1440 || y < 0 || y > 900) throw new Error(`Resource outside viewport: ${key}`);
  }
  await page.screenshot({ path: 'artifacts/mock-world.png' });
  const water = debug.targets.water;
  await page.mouse.move(water.x, water.y);
  await page.getByRole('tooltip').waitFor({ state: 'visible' });
  const tooltip = await page.getByRole('tooltip').innerText();
  if (!tooltip.includes('L')) throw new Error(`Water tooltip missing units: ${tooltip}`);
  await page.screenshot({ path: 'artifacts/water-tooltip.png' });
  await page.mouse.move(10, 450);
  await page.getByRole('button', { name: 'Agent 對話', exact: true }).click();
  await page.screenshot({ path: 'artifacts/agent-conversation.png' });
  if (errors.length) throw new Error(errors.join('\n'));
  const report = { passed: true, checks: 12, plot_count: debug.plot_count, resources: Object.keys(debug.targets), tooltip, errors };
  await writeFile('artifacts/frontend_smoke.json', JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
} finally {
  await browser.close();
}
