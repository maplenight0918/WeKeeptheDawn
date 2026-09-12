// Isolated local services; fixture Agents only, never a live provider call.
import { spawn } from 'node:child_process';
import { mkdir } from 'node:fs/promises';
import { once } from 'node:events';
import { createServer } from 'node:net';
import { chromium } from '../frontend/node_modules/playwright-core/index.mjs';
import { checkPlanningEmergency } from './planning_emergency_browser.mjs';

const processes = [];
const actions = process.argv.includes('--actions');
const targetTick = actions ? 40 : 2;
async function assertFree(port) {
  const probe = createServer();
  await new Promise((resolve, reject) => { probe.once('error', reject); probe.listen(port, '127.0.0.1', resolve); });
  await new Promise(resolve => probe.close(resolve));
}
function start(cmd, args, options = {}) {
  const child = spawn(cmd, args, { stdio: ['ignore', 'pipe', 'pipe'], ...options });
  child.output = '';
  child.stdout.on('data', data => { child.output += data; });
  child.stderr.on('data', data => { child.output += data; });
  processes.push(child);
  return child;
}
async function ready(url, child) {
  for (let i = 0; i < 200; i++) {
    if (child.exitCode !== null) throw new Error(`Service exited: ${child.output}`);
    try { if ((await fetch(url)).ok) return; } catch {}
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error('Service startup timeout');
}
let browser;
try {
  await assertFree(18001);
  await assertFree(15174);
  // Add only the isolated test origin to this in-memory test app, not production CORS.
  const bootstrap = "from backend.main import app; from fastapi.middleware.cors import CORSMiddleware; import uvicorn; app.add_middleware(CORSMiddleware, allow_origins=['http://127.0.0.1:15174'], allow_methods=['GET','POST'], allow_headers=['Content-Type']); uvicorn.run(app, host='127.0.0.1', port=18001)";
  const backend = start('.venv-bridge/bin/python', ['-c', bootstrap],
    { env: { ...process.env, GREENHOUSE_CONFIG: 'config/runtime.example.yaml', WORLD_DB: ':memory:', RESUME_WORLD: 'false' } });
  await ready('http://127.0.0.1:18001/healthz', backend);
  const frontend = start('node', ['node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', '15174'],
    { cwd: 'frontend', env: { ...process.env, VITE_API_URL: 'http://127.0.0.1:18001' } });
  await ready('http://127.0.0.1:15174', frontend);
  browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/google/chrome/chrome', headless: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [];
  const tasks = new Set();
  const summaries = [];
  page.on('websocket', socket => socket.on('framereceived', ({ payload }) => {
    const event = JSON.parse(String(payload));
    if (event.type === 'state_update' && event.payload.last_summary) {
      Object.values(event.payload.crew).forEach(crew => tasks.add(crew.current_task));
      summaries.push(event.payload.last_summary);
    }
  }));
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('http://127.0.0.1:15174', { waitUntil: 'networkidle' });
  try {
    await page.waitForFunction(() => window.__GREENHOUSE_DEBUG__?.ready, null, { timeout: 10000 });
  } catch {
    await mkdir('artifacts', { recursive: true });
    await page.screenshot({ path: 'artifacts/three-agent-bridge-init.png', fullPage: true });
    throw new Error(JSON.stringify({ page_errors: errors, body: await page.locator('body').innerText() }));
  }
  if (process.argv.includes('--emergency')) {
    await mkdir('artifacts', { recursive: true });
    const result = await checkPlanningEmergency(page);
    if (errors.length) throw new Error(errors.join('\n'));
    console.log(JSON.stringify({ passed: true, ...result, page_errors: errors }));
  } else {
  await page.getByRole('button', { name: 'Agent 對話', exact: true }).click();
  let bridge = start('.venv-bridge/bin/python', ['-m', 'agent_runner', '--game-url', 'http://127.0.0.1:18001', actions ? '--fixture-actions' : '--fixture', '--max-ticks', String(actions ? 1 : targetTick)]);
  if (actions) {
    // Regression: backend locations are plot:p20, not bare p20. Wait for the
    // actual c02 sprite to arrive at p20, rather than its old fallback p02.
    await page.waitForFunction(() => {
      const d = window.__GREENHOUSE_DEBUG__;
      if (d?.tick !== 1) return false;
      const plot = d.plot_positions.find(p => p.id === 'p20');
      const crew = d.crew_positions.find(c => c.id === 'c02');
      const scale = (d.plot_positions[1].x - d.plot_positions[0].x) / 183;
      return Math.hypot(crew.x - plot.x, crew.y - plot.y - 29 * scale) < 3;
    }, null, { timeout: 10000 });
    await page.getByRole('button', { name: '暫停', exact: true }).click();
    await page.getByRole('button', { name: '繼續', exact: true }).waitFor();
    await page.waitForFunction(() => window.__GREENHOUSE_DEBUG__?.paused);
    const pausedWorld = await (await fetch('http://127.0.0.1:18001/world')).json();
    const pausedPositions = await page.evaluate(() => window.__GREENHOUSE_DEBUG__.crew_positions);
    if (pausedWorld.tick !== 1 || pausedWorld.paused_reason !== 'player') throw new Error('Pause did not commit');
    if (bridge.exitCode === null) await once(bridge, 'exit');
    if (bridge.exitCode !== 0) throw new Error(bridge.output);
    // Restart the bridge while the player is paused. It must stay connected
    // without making a decision or unpausing the world by itself.
    bridge = start('.venv-bridge/bin/python', ['-m', 'agent_runner', '--game-url', 'http://127.0.0.1:18001', '--fixture-actions', '--max-ticks', String(targetTick - 1)]);
    await page.waitForTimeout(2300);
    const stillPaused = await (await fetch('http://127.0.0.1:18001/world')).json();
    const stillPositions = await page.evaluate(() => window.__GREENHOUSE_DEBUG__.crew_positions);
    if (JSON.stringify(pausedWorld) !== JSON.stringify(stillPaused)) throw new Error('World changed while paused');
    if (JSON.stringify(pausedPositions) !== JSON.stringify(stillPositions)) throw new Error('Crew moved while paused');
    if (bridge.exitCode !== null) throw new Error(`Bridge exited while paused: ${bridge.output}`);
    await fetch('http://127.0.0.1:18001/control', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cmd: 'speed', value: 20 }) });
    await page.getByRole('button', { name: '繼續', exact: true }).click();
    await page.getByRole('button', { name: '暫停', exact: true }).waitFor();
  }
  try {
    await page.waitForFunction(tick => window.__GREENHOUSE_DEBUG__?.tick === tick, targetTick, { timeout: 45000 });
    await page.waitForFunction(count => document.querySelectorAll('.result-facts').length === count,
      Math.min(targetTick, 3), { timeout: 10000 });
  } catch {
    await mkdir('artifacts', { recursive: true });
    await page.screenshot({ path: 'artifacts/three-agent-bridge-results.png', fullPage: true });
    throw new Error(JSON.stringify({ bridge: bridge.output, backend: backend.output, page_errors: errors,
      body: await page.locator('body').innerText() }));
  }
  if (bridge.exitCode === null) await once(bridge, 'exit');
  if (bridge.exitCode !== 0) throw new Error(bridge.output);
  if (await page.locator('.conversation-round').count() !== Math.min(targetTick, 3)) throw new Error('Conversation grouping mismatch');
  if (await page.locator('.plan-facts').count() !== Math.min(targetTick, 3)) throw new Error('Version-matched plan cards missing');
  for (const agent of ['core', 'plant', 'human']) {
    if (await page.locator(`.from-${agent}`).count() === 0) throw new Error(`Missing ${agent}`);
  }
  if (await page.locator('.kind-reflection').count() !== 0) throw new Error('Fabricated reflection');
  await page.getByRole('button', { name: '暫停', exact: true }).click();
  await page.getByRole('button', { name: '繼續', exact: true }).waitFor();
  const world = await (await fetch('http://127.0.0.1:18001/world')).json();
  if (world.tick !== targetTick || world.paused_reason !== 'player' || world.failed) throw new Error('Unexpected authoritative state');
  if (actions) {
    for (const task of ['generating', 'drinking', 'eating', 'clearing', 'planting', 'harvesting']) {
      if (!tasks.has(task)) throw new Error(`Missing actual task: ${task}`);
    }
    if (!summaries.some(s => s.water_plant.actual > 0 && s.generation.power_out > 0)) throw new Error('Equipment did not operate');
    if (!summaries.some(s => s.harvested.length > 0)) throw new Error('No actual harvest');
  }
  if (errors.length) throw new Error(errors.join('\n'));
  await mkdir('artifacts', { recursive: true });
  await page.screenshot({ path: actions ? 'artifacts/three-agent-actions.png' : 'artifacts/three-agent-bridge.png', fullPage: true });
  console.log(JSON.stringify({ passed: true, tick: world.tick, visible_conversations: Math.min(targetTick, 3), tasks: [...tasks], pause_resume_checked: actions, agents: 3, page_errors: errors }));
  }
} finally {
  if (browser) await browser.close();
  for (const child of processes.reverse()) {
    if (child.exitCode === null) {
      child.kill('SIGTERM');
      await once(child, 'exit');
    }
  }
}
