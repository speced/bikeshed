// @ts-check
const { test, expect } = require('@playwright/test');

const HTML_FILE = './tests/github/whatwg/quirks/quirks.html';

test('quirks', async ({ page }) => {
  await page.goto(HTML_FILE);

  // Expect a title "to contain" a substring.
  // await expect(page).toHaveTitle(/Playwright/);
});

test('screenshot', async ({ page }) => {
  await page.goto(HTML_FILE);
  await expect(page).toHaveScreenshot();
});
