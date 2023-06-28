// @ts-check
const { test, expect } = require('@playwright/test');

test('elementdef001', async ({ page }) => {
  await page.goto('tests/elementdef001.html');

  // Expect a title "to contain" a substring.
  // await expect(page).toHaveTitle(/Playwright/);
});

test('screenshot', async ({ page }) => {
  await page.goto('tests/elementdef001.html');
  await expect(page).toHaveScreenshot();
});

test('baz1 popup', async ({ page }) => {
  await page.goto('tests/elementdef001.html');
  await page.locator('dfn.has-dfn-panel code').getByText('baz1').click(
    // {
    // button: 'left',
    // // modifiers: ['Shift'],
    // position: { x: 2, y: 3 },
    // }
  );

  await expect(page).toHaveScreenshot();
});
