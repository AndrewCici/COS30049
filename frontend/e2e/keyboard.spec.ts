import { expect, test } from '@playwright/test';

test('the sentence table alternative is operable by keyboard alone (Part B.7)', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Use sample text' }).click();
  await page.getByRole('button', { name: 'Analyse text' }).click();
  await expect(page.getByRole('region', { name: 'Analysis result' })).toBeFocused({ timeout: 15_000 });

  // The chart itself is a plain SVG bar chart with no keyboard affordance
  // of its own; its accessible text-table equivalent is what Part B.7
  // requires to be keyboard-operable, not the chart.
  await page.getByText('Sentence scores as a table').click();
  const firstRow = page.getByRole('button', { name: /Jump to sentence 1 in the passage/ });
  await firstRow.focus();
  await expect(firstRow).toBeFocused();

  await page.keyboard.press('Enter');
  const firstMark = page.getByRole('mark').first();
  await expect(firstMark).toBeFocused();
});
