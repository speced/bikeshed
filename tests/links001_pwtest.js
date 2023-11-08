// @ts-check
const { test, expect } = require('@playwright/test');

test('links001', async ({ page }) => {
  await page.goto('./tests/links001.html');

  // Expect a title "to contain" a substring.
  // await expect(page).toHaveTitle(/Playwright/);
});

test('screenshot', async ({ page }) => {
  await page.goto('./tests/links001.html');
  await expect(page).toHaveScreenshot();
});

test('flex container dfn popup', async ({ page }) => {
  await page.goto('./tests/links001.html');
  await page.locator('span.has-dfn-panel').getByText('flex container').click();

  await expect(page).toHaveScreenshot();
});


test('flex container ref hint', async ({ page }) => {
  await page.goto('./tests/links001.html');
  await page.locator('#ref-for-flex-container').hover();

  await expect(page).toHaveScreenshot();
});
