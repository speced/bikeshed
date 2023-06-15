// @ts-check
const { test, expect } = require('@playwright/test');

test('Bikeshed testing server', async ({ page }) => {
  await page.goto('./tests/basic001.html');

  // Expect a title "to contain" a substring.
  // await expect(page).toHaveTitle(/Playwright/);
});

test('screenshot', async ({ page }) => {
  await page.goto('./tests/basic001.html');
  await expect(page).toHaveScreenshot();
});
