import { expect, test } from '@playwright/test';

test('a failed request to the backend shows a specific, actionable error', async ({ page }) => {
  // Simulate the backend being unreachable without actually stopping the
  // shared dev server the other specs in this run depend on.
  await page.route('**/api/v1/score', (route) => route.abort('connectionrefused'));

  await page.goto('/');
  await page.getByRole('button', { name: 'Use sample text' }).click();
  await page.getByRole('button', { name: 'Analyse text' }).click();

  await expect(page.getByText(/Could not reach the analysis server/)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Analyse text' })).toBeEnabled();
});
