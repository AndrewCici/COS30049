import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

/** Fails on any 'serious' or 'critical' axe violation (Part B.7); 'minor'
 * and 'moderate' findings are logged but not treated as build-breaking,
 * since axe's own docs note those categories include stylistic best
 * practices that are not WCAG failures. */
function expectNoSeriousViolations(violations: { id: string; impact?: string | null; help: string }[]) {
  const serious = violations.filter((v) => v.impact === 'serious' || v.impact === 'critical');
  if (serious.length > 0) {
    console.log('Serious/critical axe violations:', JSON.stringify(serious, null, 2));
  }
  expect(serious).toEqual([]);
}

test('detector page (empty state) has no serious accessibility violations', async ({ page }) => {
  await page.goto('/');
  const results = await new AxeBuilder({ page }).analyze();
  expectNoSeriousViolations(results.violations);
});

test('detector page (with a result, including both charts) has no serious accessibility violations', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Use sample text' }).click();
  await page.getByRole('button', { name: 'Analyse text' }).click();
  await expect(page.getByRole('heading', { level: 2, name: /Likely (AI-generated|human-made)/ }))
    .toBeVisible({ timeout: 15_000 });

  const results = await new AxeBuilder({ page }).analyze();
  expectNoSeriousViolations(results.violations);
});

test('about page has no serious accessibility violations', async ({ page }) => {
  await page.goto('/about');
  const results = await new AxeBuilder({ page }).analyze();
  expectNoSeriousViolations(results.violations);
});
