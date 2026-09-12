// One authorized paid decision after an actual browser resource edit.
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { createServer } from 'node:net';
import { mkdir } from 'node:fs/promises';
import { chromium } from '../frontend/node_modules/playwright-core/index.mjs';

if (!process.argv.includes('--allow-paid')) throw new Error('Explicit --allow-paid authorization required');
const children = [];
function start(cmd, args, options = {}) {
  const child = spawn(cmd, args, { stdio: ['ignore', 'pipe', 'pipe'], ...options });
  child.output = '';
  child.stdout.on('data', data => { child.output += data; });
  child.stderr.on('data', data => { child.output += data; });
  children.push(child);
  return child;
}
async function ready(url, child) {
  for (let i = 0; i < 150; i++) {
    if (child.exitCode !== null) throw new Error(child.output);
    try { if ((await fetch(url)).ok) return; } catch {}
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error('Startup timeout');
}
let browser;
try {
  for (const port of [18001, 15174]) {
    const probe = createServer();
    await new Promise((resolve, reject) => { probe.once('error', reject); probe.listen(port, '127.0.0.1', resolve); });
    await new Promise(resolve => probe.close(resolve));
  }
  const human = await (await fetch('http://127.0.0.1:8102/health')).json();
  const plant = await (await fetch('http://127.0.0.1:8101/health')).json();
  if (human.configured_mode !== 'live' || human.missing_setting_names.length || plant.status !== 'ok') throw new Error('Specialists not ready for live test');
  const run = start('.venv-bridge/bin/python', ['-m', 'checks.live_three_agents', '--allow-paid',
    '--game-port', '18001', '--wait-for-power-emergency']);
  await ready('http://127.0.0.1:18001/healthz', run);
  const frontend = start('node', ['node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', '15174'],
    { cwd: 'frontend', env: { ...process.env, VITE_API_URL: 'http://127.0.0.1:18001' } });
  await ready('http://127.0.0.1:15174', frontend);
  browser = await chromium.launch({ executablePath: '/opt/google/chrome/chrome', headless: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('http://127.0.0.1:15174', { waitUntil: 'networkidle' });
  await page.locator('.planning-status').waitFor();
  await page.getByRole('button', { name: 'Agent 對話', exact: true }).click();
  await page.getByRole('button', { name: '修改資源', exact: true }).click();
  await page.getByRole('spinbutton', { name: '電力', exact: true }).fill('50');
  await page.getByRole('button', { name: '套用', exact: true }).click();
  await page.getByRole('dialog', { name: '修改公共資源' }).waitFor({ state: 'hidden' });
  await mkdir('artifacts', { recursive: true });
  await page.screenshot({ path: 'artifacts/live-emergency-planning.png', fullPage: true });
  console.log('Power edited to 50 EU; one live decision in progress.');
  await page.waitForFunction(() => (window.__GREENHOUSE_DEBUG__?.tick === 1 && window.__GREENHOUSE_DEBUG__?.paused)
    || document.querySelector('.mission-status')?.textContent.includes('錯誤暫停'), null, { timeout: 450000 });
  await page.waitForTimeout(500);
  await page.screenshot({ path: 'artifacts/live-emergency-result.png', fullPage: true });
  const counts = { result_cards: await page.locator('.result-facts').count(),
    core: await page.locator('.from-core').count(), plant: await page.locator('.from-plant').count(), human: await page.locator('.from-human').count() };
  if (run.exitCode === null) await once(run, 'exit');
  console.log(run.output);
  console.log(JSON.stringify({ ...counts, page_errors: errors }));
  if (run.exitCode !== 0 || errors.length || counts.result_cards !== 1) throw new Error('Live emergency not fully confirmed');
} finally {
  if (browser) await browser.close();
  for (const child of children.reverse()) {
    if (child.exitCode === null) { child.kill('SIGTERM'); await once(child, 'exit'); }
  }
}
