import { expect, test } from '@playwright/test';

test.use({ viewport: { width: 375, height: 812 } });

test('the detector page lays out cleanly at phone width, with no horizontal scroll', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Use sample text' }).click();
  await page.getByRole('button', { name: 'Analyse text' }).click();
  await expect(page.getByRole('heading', { level: 2, name: /Likely (AI-generated|human-made)/ }))
    .toBeVisible({ timeout: 15_000 });

  const hasHorizontalScroll = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  );
  expect(hasHorizontalScroll).toBe(false);

  await page.screenshot({ path: '../docs/screenshots/phone-375px-detector-result.png', fullPage: true });
});
