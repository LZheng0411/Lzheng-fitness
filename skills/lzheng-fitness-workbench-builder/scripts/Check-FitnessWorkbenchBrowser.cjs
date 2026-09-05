// Read-only runtime gate; a fresh browser context cannot access the user's records.
const { createRequire } = require('node:module');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
async function main() {
  let chromium;
  try { ({ chromium } = require('playwright')); }
  catch { ({ chromium } = createRequire(path.join(process.cwd(), 'package.json'))('playwright')); }
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    // Optional cloud services must not be contacted by the migration gate.
    await page.route(/^https?:/, route => route.abort());
    await page.goto(pathToFileURL(path.resolve(process.argv[2])).href, { waitUntil: 'load' });
    for (const width of [375, 900, 1440]) {
      await page.setViewportSize({ width, height: 960 });
      const rail = await page.locator('#navBar').boundingBox();
      if (!rail || rail.width <= 0 || rail.x < 0 || rail.x + rail.width > width + 1)
        throw new Error('Navigation lies outside the viewport');
      if (width >= 900) {
        const main = await page.locator('body>main').boundingBox();
        if (rail.x > 1 || !main || main.x < rail.x + rail.width - 1)
          throw new Error('Sidebar is misplaced or overlaps the page');
      } else if (rail.y + rail.height > 961 || rail.y < 700) {
        throw new Error('Mobile navigation is not at the bottom of the viewport');
      }
      for (const key of ['today', 'week', 'trend', 'record', 'settings']) {
        const anchor = page.locator('#navBar a[data-k="' + key + '"]');
        if (!await anchor.isVisible()) throw new Error('Navigation not visible: ' + key);
        await anchor.click();
        if (!await page.locator('#m-' + key).isVisible()) throw new Error('Navigation did not switch: ' + key);
      }
    }
    if (errors.length || await page.evaluate(() => !window.FitnessShell || window.FitnessShell.failed))
      throw new Error('Runtime initialization failed: ' + errors.join('; '));
    console.log('FITNESS_WORKBENCH_BROWSER: PASS');
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error.message); process.exitCode = 1; });
