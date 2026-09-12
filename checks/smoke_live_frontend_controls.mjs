import { chromium } from '../frontend/node_modules/playwright-core/index.mjs';

const root = process.env.FRONTEND_ROOT || 'http://127.0.0.1:5175';
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
    return { tick: world?.tick, paused: world?.paused, speed: world?.speed,
      crew_positions: window.__GREENHOUSE_DEBUG__?.crew_positions,
      plots: world?.plots.map((plot) => [plot.id, plot.progress_ticks, plot.consecutive_unirrigated_ticks]) };
  });
}
try {
  await page.goto(root, { waitUntil: 'networkidle' });
  await page.waitForFunction(() => window.__GREENHOUSE_DEBUG__?.ready, { timeout: 30000 });
  await page.waitForFunction(async () => {
    const { useGameStore } = await import('/src/store/gameStore.ts');
    return (useGameStore.getState().world?.tick ?? 0) >= 1;
  }, { timeout: 10000 });
  await page.getByRole('button', { name: '暫停', exact: true }).click();
  await page.getByRole('button', { name: '繼續', exact: true }).waitFor();
  const paused_at = await snapshot();
  await page.waitForTimeout(700);
  const paused = await snapshot();
  if (!paused.paused || JSON.stringify(paused) !== JSON.stringify(paused_at)) {
    throw new Error('Live frontend advanced while paused');
  }
  await page.getByRole('button', { name: '×20', exact: true }).click();
  await page.waitForFunction(async () => {
    const { useGameStore } = await import('/src/store/gameStore.ts');
    const world = useGameStore.getState().world;
    return world?.paused && world.speed === 20;
  });
  const paused_fast = await snapshot();
  await page.waitForTimeout(250);
  if (JSON.stringify(await snapshot()) !== JSON.stringify(paused_fast)) {
    throw new Error('Changing live speed unpaused or animated the world');
  }
  await page.getByRole('button', { name: '繼續', exact: true }).click();
  await page.waitForFunction(async (tick) => {
    const { useGameStore } = await import('/src/store/gameStore.ts');
    return (useGameStore.getState().world?.tick ?? 0) > tick;
  }, paused_fast.tick, { timeout: 3000 });
  const resumed = await snapshot();
  if (resumed.speed !== 20 || resumed.tick <= paused_fast.tick) throw new Error('Live frontend did not resume at x20');
  console.log(JSON.stringify({ passed: true, checks: 4, paused: paused_at, resumed }));
} finally {
  await browser.close();
}
