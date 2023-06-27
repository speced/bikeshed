// @ts-check
const { test, expect } = require('@playwright/test');

const HTML_FILE = './tests/github/w3c/csswg-drafts/selectors-nonelement-1/Overview.html';

test('selectors-nonelemnt-1', async ({ page }) => {
  await page.goto(HTML_FILE);

  // Expect a title "to contain" a substring.
  // await expect(page).toHaveTitle(/Playwright/);
});

test('screenshot', async ({ page }) => {
  await page.goto(HTML_FILE);
  await expect(page).toHaveScreenshot();
});

test('screenshot dark', async ({ page }) => {
    await page.emulateMedia({ colorScheme: 'dark' });
    await page.evaluate(() => matchMedia('(prefers-color-scheme: dark)').matches); // → true
    await page.goto(HTML_FILE);
    await expect(page).toHaveScreenshot();
});
