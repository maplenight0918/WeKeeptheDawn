// Called by the isolated browser smoke; no provider or Agent decision calls.
export async function checkPlanningEmergency(page) {
  const base = 'http://127.0.0.1:18001';
  const get = async path => (await page.request.get(base + path)).json();
  const post = (path, data) => page.request.post(base + path, { data });
  const hint = page.locator('.planning-status');
  await hint.waitFor();
  if (!(await page.locator('.mission-status').innerText()).includes('Agent 規劃中')) throw new Error('Missing planning label');
  const initial = await get('/world');
  const old = await get('/decision');
  await page.waitForTimeout(2200);
  if (JSON.stringify(await get('/world')) !== JSON.stringify(initial)) throw new Error('World changed while waiting');
  await page.screenshot({ path: 'artifacts/planning-status.png', fullPage: true });

  // Hold the polling endpoint on the OLD version while the real UI edits power.
  await page.route('**/decision', route => route.fulfill({ json: old }));
  await page.getByRole('button', { name: '修改資源', exact: true }).click();
  await page.getByRole('spinbutton', { name: '電力', exact: true }).fill('0');
  await page.getByRole('button', { name: '套用', exact: true }).click();
  await page.getByRole('dialog', { name: '修改公共資源' }).waitFor({ state: 'hidden' });
  const edited = await get('/world');
  if (edited.resources.power.value !== 0 || edited.tick !== 0 || edited.failed || edited.version <= initial.version) throw new Error('Power emergency edit failed');
  await hint.waitFor({ state: 'hidden' });
  await page.waitForTimeout(1100);
  if (await hint.count()) throw new Error('Stale planning response was accepted');
  const stale = await post('/ingest/decision-plan', { request_id: old.request_id, submission_id: 'browser-stale',
    plan: { tick: old.tick, state_version: old.state_version, generation: {}, refills: [], plot_ops: [], water_production_l: 0, irrigation: [] } });
  if (stale.status() !== 409) throw new Error('Stale plan accepted after edit');
  await page.unroute('**/decision');
  await hint.waitFor();
  const fresh = await get('/decision');
  if (fresh.state_version !== edited.version || fresh.request_id === old.request_id) throw new Error('No fresh emergency request');
  await page.screenshot({ path: 'artifacts/resource-emergency-planning.png', fullPage: true });

  await page.getByRole('button', { name: '暫停', exact: true }).click();
  await hint.waitFor({ state: 'hidden' });
  await page.getByRole('button', { name: '繼續', exact: true }).click();
  await hint.waitFor();
  // Reload during planning must recover status without waiting for a new thought.
  await page.reload({ waitUntil: 'networkidle' });
  await hint.waitFor();
  await page.context().setOffline(true);
  await hint.waitFor({ state: 'hidden' });
  await page.context().setOffline(false);
  await hint.waitFor({ timeout: 15000 });

  const failing = await get('/decision');
  const failedNotice = await post('/ingest/decision-failure', { request_id: failing.request_id });
  if (failedNotice.status() !== 202) throw new Error('Failure notice rejected');
  await page.waitForFunction(() => document.querySelector('.mission-status')?.textContent.includes('錯誤暫停'));
  await hint.waitFor({ state: 'hidden' });
  await page.getByRole('button', { name: '繼續', exact: true }).click();
  await hint.waitFor();

  await page.getByRole('button', { name: '修改資源', exact: true }).click();
  await page.getByRole('spinbutton', { name: '氧氣', exact: true }).fill('0');
  await page.getByRole('button', { name: '套用', exact: true }).click();
  await page.locator('.failure-card').waitFor();
  await hint.waitFor({ state: 'hidden' });
  const failed = await get('/world');
  if (!failed.failed || failed.tick !== 0 || Object.values(failed.crew).some(c => c.alive)) throw new Error('Oxygen-zero death incorrect');
  if (await get('/decision')) throw new Error('Decision started for failed world');
  await page.screenshot({ path: 'artifacts/resource-emergency-oxygen-zero.png', fullPage: true });
  return { planning: true, stale_status_rejected: true, power_edit: true, oxygen_zero: true,
    pause_resume: true, error_pause: true, reload: true, network_recovery: true, paid_calls: 0 };
}
