const { defineConfig } = require('@playwright/test');
module.exports = defineConfig({
  testDir: './tests/browser',
  timeout: 45000,
  workers: 1,
  fullyParallel: false,
  use: { browserName: 'chromium', headless: true },
  reporter: 'list',
});
