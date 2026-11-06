import { expect, test } from '@playwright/test';

// Part B.6: verified at 375 (phone), 768 (tablet) and 1280 (desktop) px.
// 375px with a full result rendered is also covered, with a saved
// screenshot, by phone-viewport.spec.ts.
for (const width of [375, 768, 1280]) {
  test(`no horizontal scroll at ${width}px wide`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/');
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
    );
    expect(overflow).toBe(false);
  });
}
