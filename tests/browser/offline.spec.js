const { test, expect } = require('@playwright/test');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const http = require('node:http');
const { spawnSync } = require('node:child_process');
const { pathToFileURL } = require('node:url');
const repo = path.resolve(__dirname, '../..');
let server, base, fixture;

test.beforeAll(async () => {
  fixture = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'fw-')), 'project');
  const built = spawnSync(process.env.PYTHON || 'python', ['-B', path.join(repo, 'skills/lzheng-fitness-workbench-builder/scripts/Initialize-FitnessWorkbench.py'), '--target', fixture, '--brand', 'TEST', '--athlete', '匿名测试'], { encoding: 'utf8', env: { ...process.env, PYTHONUTF8: '1', PYTHONDONTWRITEBYTECODE: '1' } });
  if (built.status !== 0) throw new Error(built.stdout + built.stderr);
  let html = fs.readFileSync(path.join(fixture, '健身工作台.html'), 'utf8');
  // Test-only synthetic prescription; never copied into the shipped template or personal project.
  html = html.replace(/(<script id="workbench-data" type="application\/json">)([\s\S]*?)(<\/script>)/, (_, a, raw, z) => {
    const data = JSON.parse(raw);
    data.days['测试A'] = { title: '匿名浏览器验收', exercises: [{ name: '测试卧推', w: '20kg', d: '1×5 @7', planned_sets: 1 }] };
    return a + JSON.stringify(data) + z;
  });
  const hook = `window.__fitnessTest={openTraining,openNutrition,openTrainingArchive,trainingState,trainingPlanRows,trainingGoFeedback,renderNutrition,renderNutritionProgress,nutritionCloud,D,offlineStore,refreshOfflineMeals,taState,openOfflineMeal,trainingLocalKey};`;
  const end = html.lastIndexOf('})();');
  html = html.slice(0, end) + hook + html.slice(end);
  fs.writeFileSync(path.join(fixture, 'browser-test.html'), html);
  server = http.createServer((req, res) => {
    const rel = decodeURIComponent((req.url || '/').split('?')[0]);
    if (rel === '/' || rel === '/index.html') { res.setHeader('Content-Type', 'text/html; charset=utf-8'); res.end(html); return; }
    const file = path.resolve(fixture, '.' + rel);
    if (!file.startsWith(fixture + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) { res.writeHead(404); res.end(); return; }
    const mime = { '.png': 'image/png', '.mp4': 'video/mp4', '.html': 'text/html; charset=utf-8' }[path.extname(file)] || 'application/octet-stream';
    res.setHeader('Content-Type', mime); fs.createReadStream(file).pipe(res);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  base = `http://127.0.0.1:${server.address().port}`;
});
test.afterAll(async () => { if (server) await new Promise(resolve => server.close(resolve)); });

test.beforeEach(async ({ page }) => {
  page.__errors = []; page.__external = [];
  page.on('pageerror', e => page.__errors.push(e.message));
  page.on('request', r => { if (/^https?:/.test(r.url()) && !r.url().startsWith(base)) page.__external.push(r.url()); });
  await page.goto(base);
  await page.waitForFunction(() => !!window.__fitnessTest);
});
test.afterEach(async ({ page }) => {
  expect(page.__errors).toEqual([]);
  expect(page.__external).toEqual([]);
});

async function completeTraining(page) {
  await page.evaluate(async () => {
    const h = window.__fitnessTest;
    await h.openTraining('测试A');
    h.trainingState.exercises.forEach(ex => { ex.done = true; ex.groups.forEach(g => { g.weight = '20'; g.rows.forEach(r => { r.reps = '5'; r.rpe = '7'; }); }); });
    h.trainingGoFeedback();
  });
  await page.locator('#trainingNotes').fill('匿名完成记录，不修改计划');
  await page.locator('#trainingFinish').click();
  await expect(page.locator('#trainingFinishStatus')).toContainText('已保存本机正式记录');
}
async function newMeal(page, photo = false) {
  await page.evaluate(() => window.__fitnessTest.openNutrition());
  await page.locator('#nutritionMealTypes button').first().click();
  await page.locator('#nutritionMealName').fill('匿名测试餐');
  await page.locator('#nutritionMealNote').fill('自己的记录，尚未估算');
  if (photo) await page.locator('#nutritionPhotoAlbumInput').setInputFiles({ name: 'example.png', mimeType: 'image/png', buffer: fs.readFileSync(path.join(repo, 'skills/lzheng-fitness-plan/assets/header-lineart.png')) });
  if (photo) await expect(page.locator('#nutritionMealFiles')).toContainText('1');
  await expect(page.locator('#nutritionMealName')).toHaveValue('匿名测试餐');
  await expect(page.locator('#nutritionMealNote')).toHaveValue('自己的记录，尚未估算');
  await page.locator('#nutritionMealSave').click();
  await expect(page.locator('#nutritionMealList')).toContainText('尚无营养数值');
}
async function fillCandidate(page, calories) {
  for (const [id, value] of Object.entries({ offlineCalories: calories, offlineCarbs: '30', offlineProtein: '20', offlineFat: '10', offlineSource: '测试食品标签；人工录入，不代表 AI 识别' })) await page.locator('#' + id).fill(String(value));
  await page.locator('#offlineMealCandidate button').click();
  await expect(page.locator('#nutritionMealList')).toContainText('待确认入账');
}

test('training completion survives reload; archive correction, restore, and plan isolation', async ({ page }) => {
  const plan = await page.evaluate(() => JSON.stringify(window.__fitnessTest.D));
  await completeTraining(page);
  await page.reload();
  await page.waitForFunction(() => !!window.__fitnessTest);
  await page.evaluate(() => window.__fitnessTest.openTrainingArchive());
  await expect(page.locator('#taAccountState')).toContainText('1 次力量训练');
  await expect(page.locator('#taVolume')).toContainText('有效组');
  await page.locator('#taRecordList button').first().click();
  await page.locator('#taEditOpen').click();
  await page.locator('#taEditList input').first().fill('22.5');
  await page.locator('#taEditReview').click();
  await page.locator('#taConfirmSave').click();
  await expect(page.locator('#taDetailBody')).toContainText('22.5kg');
  page.once('dialog', dialog => dialog.accept());
  await page.locator('#taRestore').click();
  await expect(page.locator('#taDetailBody')).toContainText('20kg');
  expect(await page.evaluate(() => JSON.stringify(window.__fitnessTest.D))).toBe(plan);
  const sessions = await page.evaluate(() => window.__fitnessTest.offlineStore.all('session'));
  expect(sessions).toHaveLength(1);
  expect(sessions[0].revisions).toHaveLength(2);
});

test('meals persist photos, distinguish candidates/confirmation, and keep served estimates after leftovers', async ({ page }) => {
  await newMeal(page, true);
  await page.reload(); await page.waitForFunction(() => !!window.__fitnessTest);
  await page.evaluate(() => window.__fitnessTest.openNutrition());
  await page.locator('#nutritionMealList button').first().click();
  await expect(page.locator('#nutritionPreviewImage')).toBeVisible();
  expect(await page.locator('#nutritionPreviewImage').evaluate(img => img.naturalWidth)).toBeGreaterThan(0);
  await fillCandidate(page, '400');
  let meal = (await page.evaluate(() => window.__fitnessTest.offlineStore.all('meal')))[0];
  expect(meal.confirmed_nutrition).toBeNull();
  await page.locator('#nutritionConfirmEstimate').click();
  await expect(page.locator('#nutritionMealList')).toContainText('已确认入账 · 400 kcal');
  page.once('dialog', dialog => dialog.accept()); await page.locator('#nutritionUnconfirmMeal').click();
  await expect(page.locator('#nutritionMealList')).toContainText('待确认入账');
  await page.locator('#nutritionOpenConsumption').click();
  await page.locator('#nutritionMealNote').fill('剩了一部分，实际摄入需要重新填写');
  await page.locator('#nutritionAfterPhotoAlbumInput').setInputFiles({ name: 'after.png', mimeType: 'image/png', buffer: fs.readFileSync(path.join(repo, 'skills/lzheng-fitness-plan/assets/header-lineart.png')) });
  await expect(page.locator('#nutritionMealFiles')).toContainText('1 张待保存照片');
  await expect(page.locator('#nutritionMealNote')).toHaveValue('剩了一部分，实际摄入需要重新填写');
  await page.locator('#nutritionMealSave').click();
  await expect(page.locator('#offlineMealCandidateTitle')).toContainText('实际吃下');
  await expect(page.locator('#nutritionConfirmEstimate')).toBeHidden();
  await fillCandidate(page, '250'); await page.locator('#nutritionConfirmEstimate').click();
  await expect(page.locator('#nutritionMealList')).toContainText('250 kcal');
  meal = (await page.evaluate(() => window.__fitnessTest.offlineStore.all('meal')))[0];
  expect(meal.estimate.best_estimate.calories).toBe(400);
  expect(meal.consumed_estimate.best_estimate.calories).toBe(250);
  expect(meal.confirmed_nutrition.confirmed_source).toBe('user_entered');
  expect(meal.photos).toHaveLength(1);
  expect(meal.after_photos).toHaveLength(1);
  await page.reload(); await page.waitForFunction(() => !!window.__fitnessTest);
  await page.evaluate(() => window.__fitnessTest.openNutrition());
  await page.locator('#nutritionMealList button').first().click();
  await expect(page.locator('#offlineMealPhotos img')).toHaveCount(2);
  await expect(page.locator('#offlineMealPhotos')).toContainText('饭后照片');
});

test('only confirmed meals affect today totals, and undo removes them', async ({ page }) => {
  await newMeal(page); await fillCandidate(page, '400');
  const renderTotals = () => page.evaluate(() => window.__fitnessTest.renderNutritionProgress({ calories: 2000, carbs: 250, protein: 100, fat: 60 }));
  await renderTotals(); await expect(page.locator('#nutritionConsumedCalories')).toHaveText('0');
  await page.locator('#nutritionConfirmEstimate').click();
  await expect(page.locator('#nutritionMealList')).toContainText('已确认入账');
  await renderTotals(); await expect(page.locator('#nutritionConsumedCalories')).toHaveText('400');
  page.once('dialog', d => d.accept()); await page.locator('#nutritionUnconfirmMeal').click();
  await expect(page.locator('#nutritionMealList')).toContainText('待确认入账');
  await renderTotals(); await expect(page.locator('#nutritionConsumedCalories')).toHaveText('0');
});

test('failed photo write rolls back meal metadata instead of claiming saved', async ({ page }) => {
  await page.evaluate(() => {
    const original = IDBObjectStore.prototype.put;
    IDBObjectStore.prototype.put = function (row) { if (row.kind === 'photo') throw new DOMException('quota', 'QuotaExceededError'); return original.call(this, row); };
  });
  await page.evaluate(() => window.__fitnessTest.openNutrition());
  await page.locator('#nutritionMealTypes button').first().click();
  await page.locator('#nutritionPhotoAlbumInput').setInputFiles({ name: 'example.png', mimeType: 'image/png', buffer: fs.readFileSync(path.join(repo, 'skills/lzheng-fitness-plan/assets/header-lineart.png')) });
  await expect(page.locator('#nutritionMealFiles')).toContainText('1');
  await page.locator('#nutritionMealSave').click();
  await expect(page.locator('#offlineMealMessage')).toContainText('尚未保存');
  expect(await page.evaluate(() => window.__fitnessTest.offlineStore.all('meal'))).toEqual([]);
  expect(await page.evaluate(() => window.__fitnessTest.offlineStore.all('photo'))).toEqual([]);
});

test('configured cloud outage does not silently create local completed records', async ({ page }) => {
  await page.evaluate(async () => {
    const h = window.__fitnessTest; h.nutritionCloud.enabled = true; h.nutritionCloud.ready = false;
    await h.openTraining('测试A');
    h.trainingState.exercises.forEach(ex => { ex.done = true; ex.groups.forEach(g => { g.weight = '20'; g.rows.forEach(r => { r.reps = '5'; r.rpe = '7'; }); }); });
    h.trainingGoFeedback();
  });
  await page.locator('#trainingFinish').click();
  await expect(page.locator('#trainingFinishStatus')).toContainText('草稿仍保存在本机');
  expect(await page.evaluate(() => window.__fitnessTest.trainingState.completed)).toBe(false);
  expect(await page.evaluate(() => window.__fitnessTest.offlineStore.all('session'))).toEqual([]);
});

test('storage rejects malformed values and stale writes, isolates instances, restores a private backup', async ({ page }) => {
  await completeTraining(page); await newMeal(page, true);
  const result = await page.evaluate(async () => {
    const store = window.__fitnessTest.offlineStore, session = (await store.all('session'))[0], meal = (await store.all('meal'))[0];
    const reject = async action => { try { await action(); return false; } catch { return true; } };
    const invalid = await reject(() => store.correctSession(session.id, session.revision, [{ set_id: session.exercises[0].sets[0].id, reps: 1.5 }]));
    const blank = await reject(() => store.candidate(meal.id, meal.revision, 'before', { calories: '', carbs_g: 0, protein_g: 0, fat_g: 0 }, '标签'));
    const updated = await store.candidate(meal.id, meal.revision, 'before', { calories: 10, carbs_g: 1, protein_g: 1, fat_g: 1 }, '标签');
    const stale = await reject(() => store.confirmMeal(meal.id, meal.revision));
    const backup = await store.exportBackup(), other = FitnessLocal.create('isolated-browser-test');
    const empty = await other.all('session'); await other.importBackup(backup);
    const refuseOverwrite = await reject(() => other.importBackup(backup));
    const photos = await other.all('photo');
    return { invalid, blank, stale, empty, refuseOverwrite, photoBytes: photos[0].blob.size, restored: await other.all('session'), unchanged: await store.read('session', session.id), version: updated.revision };
  });
  expect(result.invalid && result.blank && result.stale && result.refuseOverwrite).toBe(true);
  expect(result.empty).toEqual([]); expect(result.restored).toHaveLength(1);
  expect(result.unchanged.revision).toBe(1);
  expect(result.photoBytes).toBeGreaterThan(0);
});

test('opening an HTML file directly retains completed training and meals after reload', async ({ page }) => {
  await page.goto(pathToFileURL(path.join(fixture, 'browser-test.html')).href);
  await completeTraining(page); await newMeal(page);
  await page.reload(); await page.waitForFunction(() => !!window.__fitnessTest);
  await page.evaluate(() => window.__fitnessTest.openNutrition());
  await expect(page.locator('#nutritionMealList')).toContainText('匿名测试餐');
  expect(await page.evaluate(() => window.__fitnessTest.offlineStore.all('session'))).toHaveLength(1);
});

test('duplicate completion cannot overwrite another tab and plan-version changes keep records', async ({ page }) => {
  await completeTraining(page);
  const result = await page.evaluate(async () => {
    const h = window.__fitnessTest, session = (await h.offlineStore.all('session'))[0];
    let rejected = false; try { await h.offlineStore.saveSession({ ...session, notes: 'must not overwrite' }); } catch { rejected = true; }
    h.D.meta.source_version = 'new-version';
    const same = FitnessLocal.create(String(h.D.system.instance_id));
    return { rejected, records: await same.all('session') };
  });
  expect(result.rejected).toBe(true); expect(result.records).toHaveLength(1);
  expect(result.records[0].notes).toBe('匿名完成记录，不修改计划');
});

test('failed database transaction never reports completed training', async ({ page }) => {
  await page.evaluate(async () => {
    const h = window.__fitnessTest; await h.openTraining('测试A');
    h.trainingState.exercises.forEach(ex => { ex.done = true; ex.groups.forEach(g => { g.weight = '20'; g.rows.forEach(r => { r.reps = '5'; r.rpe = '7'; }); }); });
    h.trainingGoFeedback();
    IDBObjectStore.prototype.add = function () { throw new DOMException('quota', 'QuotaExceededError'); };
  });
  await page.locator('#trainingFinish').click();
  await expect(page.locator('#trainingFinishStatus')).toContainText('保存未完成');
  expect(await page.evaluate(() => window.__fitnessTest.trainingState.completed)).toBe(false);
  expect(await page.evaluate(() => window.__fitnessTest.offlineStore.all('session'))).toEqual([]);
});

test('mobile local meal form and desktop navigation remain usable', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 375, height: 812 }); await newMeal(page);
  await expect(page.locator('#offlineMealCandidate')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
  await page.screenshot({ path: testInfo.outputPath('mobile-local-meal.png'), fullPage: true });
  await page.setViewportSize({ width: 1440, height: 960 });
  await page.locator('#nutritionBack').click();
  await page.locator('#navBar a').first().click();
  await expect(page.locator('#navBar a')).toHaveCount(5);
  for (const link of await page.locator('#navBar a').all()) await expect(link).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('desktop-workbench.png'), fullPage: true });
});

test('navigation survives broken JSON and a business script syntax error', async ({ page }) => {
  const source = fs.readFileSync(path.join(fixture, 'browser-test.html'), 'utf8');
  for (const mode of ['json', 'script']) {
    const html = mode === 'json'
      ? source.replace(/(<script id="workbench-data" type="application\/json">)[\s\S]*?(<\/script>)/, '$1{$2')
      : source.replace('var D = JSON.parse', 'var deliberately broken syntax; var D = JSON.parse');
    await page.route(base + '/fault-' + mode, route => route.fulfill({ contentType: 'text/html', body: html }));
    await page.goto(base + '/fault-' + mode);
    await expect(page.locator('#workbenchError')).toBeVisible();
    for (const width of [375, 899, 900, 1440]) {
      await page.setViewportSize({ width, height: 960 });
      for (const key of ['today', 'week', 'trend', 'record', 'settings']) {
        const link = page.locator('#navBar a[data-k="' + key + '"]');
        await expect(link).toBeVisible(); await link.click();
        await expect(page.locator('#m-' + key)).toBeVisible();
        await expect(page.locator('main>section.on')).toHaveCount(1);
        await expect(link).toHaveAttribute('aria-current', 'page');
      }
    }
  }
  expect(page.__errors).toHaveLength(2);
  expect(page.__errors[0]).toMatch(/JSON|property name/);
  expect(page.__errors[1]).toMatch(/Unexpected identifier/);
  page.__errors = []; // Only the two deliberately injected failures were expected.
});

test('a failed training render leaves navigation and other pages available', async ({ page }) => {
  const source = fs.readFileSync(path.join(fixture, 'browser-test.html'), 'utf8');
  const html = source.replace('function renderTodayContent(name){', 'function renderTodayContent(name){throw new Error("controlled training failure");');
  await page.route(base + '/render-failure', route => route.fulfill({ contentType: 'text/html', body: html }));
  await page.goto(base + '/render-failure');
  await expect(page.locator('#workbenchError')).toBeVisible();
  await page.locator('#navBar a[data-k="settings"]').click();
  await expect(page.locator('#howNote')).toContainText('查看训练');
  await page.locator('#navBar a[data-k="week"]').click();
  await expect(page.locator('#dayGrid')).not.toBeEmpty();
});

test('null display version and malformed phase data do not prevent other modules starting', async ({ page }) => {
  const source = fs.readFileSync(path.join(fixture, 'browser-test.html'), 'utf8');
  const html = source.replace(/(<script id="workbench-data" type="application\/json">)([\s\S]*?)(<\/script>)/, (_, a, raw, b) => {
    const data = JSON.parse(raw); data.meta.source_version = null; data.phases = null;
    return a + JSON.stringify(data) + b;
  });
  await page.route(base + '/bad-phases', route => route.fulfill({ contentType: 'text/html', body: html }));
  await page.goto(base + '/bad-phases');
  await expect(page.locator('#workbenchError')).toContainText('周期阶段');
  await expect(page.locator('#verChip')).toContainText('待确认');
  await page.locator('#navBar a[data-k="settings"]').click();
  await expect(page.locator('#howNote')).toContainText('查看训练');
});

test('desktop nutrition preserves navigation, protects drafts, and clears page mode on exit', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 960 });
  await page.evaluate(() => window.__fitnessTest.openNutrition());
  await expect(page.locator('#navBar')).toBeVisible();
  const rail = await page.locator('#navBar').boundingBox();
  const main = await page.locator('body>main').boundingBox();
  expect(main.x).toBeGreaterThanOrEqual(rail.x + rail.width);
  await page.screenshot({ path: testInfo.outputPath('desktop-nutrition-sidebar.png'), fullPage: true });
  await page.locator('#nutritionMealTypes button').first().click();
  await page.locator('#nutritionMealName').fill('尚未保存的编辑');
  page.once('dialog', d => d.dismiss());
  await page.locator('#navBar a[data-k="week"]').click();
  await expect(page.locator('#m-nutrition')).toBeVisible();
  await expect(page.locator('#nutritionMealName')).toHaveValue('尚未保存的编辑');
  page.once('dialog', d => d.accept());
  await page.locator('#navBar a[data-k="week"]').click();
  await expect(page.locator('#m-week')).toBeVisible();
  await expect(page.locator('body')).not.toHaveClass(/nutrition-open|training-record-open/);
  await page.setViewportSize({ width: 375, height: 812 });
  await page.evaluate(() => window.__fitnessTest.openNutrition());
  await expect(page.locator('#navBar')).toBeHidden();
  await page.locator('#nutritionBack').click();
  await expect(page.locator('#navBar')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
});

test('real v3.1.1 upgrades in the same file without losing records, photos, or instance identity', async ({ page }) => {
  test.setTimeout(120000);
  const { gunzipSync } = require('node:zlib');
  const formal = path.join(fixture, '健身工作台.html');
  const before = fs.readFileSync(formal);
  const testSource = fs.readFileSync(path.join(fixture, 'browser-test.html'), 'utf8');
  const dataRe = /(<script id="workbench-data" type="application\/json">)([\s\S]*?)(<\/script>)/;
  const raw = testSource.match(dataRe)[2];
  let legacy = gunzipSync(fs.readFileSync(path.join(repo, 'tests/fixtures/ui-history/v3.1.1.html.gz'))).toString('utf8');
  legacy = legacy.replaceAll('__FWB_BRAND__', 'TEST').replace(dataRe, (_, a, b, c) => a + raw + c);
  const hook = testSource.match(/window\.__fitnessTest=\{[^;]+;/)[0];
  const end = legacy.lastIndexOf('})();');
  const withHook = legacy.slice(0, end) + hook + legacy.slice(end);
  const backup = path.join(path.dirname(fixture), 'ui-backups');
  try {
    fs.writeFileSync(formal, withHook);
    await page.goto(pathToFileURL(formal).href);
    await completeTraining(page); await newMeal(page, true);
    const oldBackup = await page.evaluate(() => window.__fitnessTest.offlineStore.exportBackup());
    // Remove the test hook before migration: only official shells may be auto-upgraded.
    fs.writeFileSync(formal, legacy);
    const result = spawnSync(process.env.PYTHON || 'python', ['-B', path.join(repo, 'skills/lzheng-fitness-workbench-builder/scripts/Upgrade-FitnessWorkbenchUi.py'), '--project', fixture, '--backup-dir', backup, '--apply'], { cwd: repo, encoding: 'utf8', timeout: 90000, env: { ...process.env, PYTHONUTF8: '1', PYTHONDONTWRITEBYTECODE: '1' } });
    expect(result.status, result.stdout + result.stderr).toBe(0);
    const receipt = JSON.parse(result.stdout);
    expect(receipt.ui_upgraded && receipt.browser_verified).toBe(true);
    expect(receipt.data_refreshed || receipt.browser_records_backed_up).toBe(false);
    expect(fs.readFileSync(formal, 'utf8').match(dataRe)[2]).toBe(raw);
    await page.reload();
    const restored = await page.evaluate(async () => {
      const data = JSON.parse(document.getElementById('workbench-data').textContent);
      const store = FitnessLocal.create(data.system.instance_id);
      return { backup: await store.exportBackup(), sessions: await store.all('session'), meals: await store.all('meal'), photos: (await store.all('photo')).map(p => p.blob.size), instance: data.system.instance_id };
    });
    expect(restored.instance).toBe(JSON.parse(raw).system.instance_id);
    expect(restored.sessions).toHaveLength(1); expect(restored.meals).toHaveLength(1);
    expect(restored.photos[0]).toBeGreaterThan(0);
    // Export includes timestamps; compare the persistent records and attachments themselves.
    expect(restored.backup.records).toEqual(oldBackup.records);
    for (const key of ['today', 'week', 'trend', 'record', 'settings']) {
      await page.locator('#navBar a[data-k="' + key + '"]').click();
      await expect(page.locator('#m-' + key)).toBeVisible();
    }
  } finally { fs.writeFileSync(formal, before); }
});

test('public page and installer agree on the explicit Agent protocol', async ({ page }) => {
  expect(await page.evaluate(() => FitnessLocal.agentUri)).toBe('lzheng-fitness-agent://run');
  const installer = fs.readFileSync(path.join(repo, 'integrations/cloudbase/local-agent/Install-NutritionLocalAgent.ps1'), 'utf8');
  expect(installer).toContain("$ProtocolName='lzheng-fitness-agent'");
  expect(fs.readFileSync(path.join(repo, 'skills/lzheng-fitness-workbench-builder/assets/workbench-template.html'), 'utf8')).not.toContain('lzheng-nutrition-agent://');
});

for (const release of ['v2.3.0', 'v2.3.1', 'v3.1.0']) {
  test('official ' + release + ' shell migrates through the real browser gate', async ({ page }) => {
    test.setTimeout(120000);
    const { gunzipSync } = require('node:zlib');
    const formal = path.join(fixture, '健身工作台.html');
    const before = fs.readFileSync(formal);
    const dataRe = /(<script id="workbench-data" type="application\/json">)([\s\S]*?)(<\/script>)/;
    const raw = before.toString('utf8').match(dataRe)[2];
    const old = gunzipSync(fs.readFileSync(path.join(repo, 'tests/fixtures/ui-history/' + release + '.html.gz'))).toString('utf8')
      .replaceAll('__FWB_BRAND__', 'TEST').replace(dataRe, (_, a, b, c) => a + raw + c);
    try {
      fs.writeFileSync(formal, old);
      const result = spawnSync(process.env.PYTHON || 'python', ['-B', path.join(repo, 'skills/lzheng-fitness-workbench-builder/scripts/Upgrade-FitnessWorkbenchUi.py'), '--project', fixture, '--backup-dir', path.join(path.dirname(fixture), 'ui-history-backups'), '--apply'], { cwd: repo, encoding: 'utf8', timeout: 90000, env: { ...process.env, PYTHONUTF8: '1', PYTHONDONTWRITEBYTECODE: '1' } });
      expect(result.status, result.stdout + result.stderr).toBe(0);
      const receipt = JSON.parse(result.stdout);
      expect(receipt.source_release).toBe(release);
      expect(receipt.ui_upgraded && receipt.browser_verified).toBe(true);
      expect(fs.readFileSync(formal, 'utf8').match(dataRe)[2]).toBe(raw);
      await page.goto(pathToFileURL(formal).href);
      await page.locator('#navBar a[data-k="settings"]').click();
      await expect(page.locator('#m-settings')).toBeVisible();
    } finally { fs.writeFileSync(formal, before); }
  });
}
