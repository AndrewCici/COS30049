import { expect, test } from '@playwright/test';

test('pastes text, analyses it, and sees a verdict with confidence and CI', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Use sample text' }).click();
  await page.getByRole('button', { name: 'Analyse text' }).click();

  const verdictHeading = page.getByRole('heading', { level: 2, name: /Likely (AI-generated|human-made)/ });
  await expect(verdictHeading).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole('region', { name: 'Analysis result' })).toBeFocused();

  await expect(page.getByText('Confidence', { exact: true })).toBeVisible();
  await expect(page.getByText('95% confidence interval', { exact: true })).toBeVisible();
  await expect(page.getByText('Which sentences drive this score?')).toBeVisible();
  await expect(page.getByText('Sentence-level analysis')).toBeVisible();
  await expect(page.getByText('How does this text compare with others checked this session?')).toBeVisible();
});
