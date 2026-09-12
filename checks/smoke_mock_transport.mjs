import { chromium } from '../frontend/node_modules/playwright-core/index.mjs';

const root = process.env.FRONTEND_ROOT || 'http://127.0.0.1:5174';
const browser = await chromium.launch({
  ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}),
  headless: true,
  args: ['--no-sandbox', '--disable-dev-shm-usage', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
});
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
async function snapshot() {
  return page.evaluate(async () => {
    const { useGameStore } = await import('/src/store/gameStore.ts');
    const world = useGameStore.getState().world;
    return {
      tick: world?.tick,
      paused: world?.paused,
      speed: world?.speed,
      crew_positions: window.__GREENHOUSE_DEBUG__?.crew_positions,
      plot_progress: world?.plots.map((plot) => [plot.id, plot.progress_ticks, plot.consecutive_unirrigated_ticks]),
    };
  });
}
try {
  await page.goto(`${root}/?mock=1`, { waitUntil: 'networkidle' });
  await page.waitForFunction(() => window.__GREENHOUSE_DEBUG__?.ready);
  await page.getByRole('button', { name: '×20', exact: true }).click();
  await page.waitForFunction(() => window.__GREENHOUSE_DEBUG__?.tick >= 6, { timeout: 3000 });
  const progressed = await snapshot();
  await page.getByRole('button', { name: '暫停', exact: true }).click();
  await page.getByRole('button', { name: '繼續', exact: true }).waitFor();
  const paused_at = await snapshot();
  const bubble = page.locator('.world-bubble').first();
  if (await bubble.count()) {
    const animation_state = await bubble.evaluate((node) => getComputedStyle(node).animationPlayState);
    if (animation_state !== 'paused') throw new Error(`Paused bubble animation is ${animation_state}`);
  }
  await page.waitForTimeout(600);
  const paused = await snapshot();
  if (!paused.paused || paused.tick !== paused_at.tick || paused.speed !== 20
      || JSON.stringify(paused.crew_positions) !== JSON.stringify(paused_at.crew_positions)
      || JSON.stringify(paused.plot_progress) !== JSON.stringify(paused_at.plot_progress)) {
    throw new Error('Paused mock changed authoritative or animated world state');
  }
  await page.getByRole('button', { name: '繼續', exact: true }).click();
  await page.waitForFunction((tick) => window.__GREENHOUSE_DEBUG__?.tick > tick, paused.tick, { timeout: 3000 });
  const resumed = await snapshot();
  if (resumed.tick <= paused.tick || resumed.speed !== 20) throw new Error('Mock did not resume at selected speed');
  console.log(JSON.stringify({ passed: true, checks: 6, progressed, paused, resumed }));
} finally {
  await browser.close();
}
