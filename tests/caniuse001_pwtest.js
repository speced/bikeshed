// @ts-check
const { test, expect } = require('@playwright/test');

test('caniuse001', async ({ page }) => {
  await page.goto('./caniuse001.html');

  // Expect a title "to contain" a substring.
  // await expect(page).toHaveTitle(/Playwright/);
});

test('screenshot', async ({ page }) => {
  await page.goto('tests/caniuse001.html');
  await expect(page).toHaveScreenshot();
});

test('caniuse popup', async ({ page }) => {
  await page.goto('tests/caniuse001.html');
  await page.locator('details.caniuse-status').click(
    // {
    // button: 'left',
    // // modifiers: ['Shift'],
    // position: { x: 2, y: 3 },
    // }
  );

  await expect(page).toHaveScreenshot();
});
