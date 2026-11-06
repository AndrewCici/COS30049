import { expect, test } from '@playwright/test';

test('a too-short passage shows an inline reason and disables submission', async ({ page }) => {
  await page.goto('/');
  const field = page.getByLabel('Text to analyse');
  await field.fill('too short');

  await expect(page.getByText(/Text is too short: enter at least 20 characters/)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Analyse text' })).toBeDisabled();
});

test('whitespace-only text is rejected the same way as empty text', async ({ page }) => {
  await page.goto('/');
  const field = page.getByLabel('Text to analyse');
  await field.fill('                              ');

  await expect(page.getByText('Text cannot be only whitespace.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Analyse text' })).toBeDisabled();
});

test('a valid-length passage clears the validation message and enables submission', async ({ page }) => {
  await page.goto('/');
  const field = page.getByLabel('Text to analyse');
  await field.fill('This passage is comfortably over the twenty character minimum.');

  await expect(page.getByText(/Text is too short/)).not.toBeVisible();
  await expect(page.getByRole('button', { name: 'Analyse text' })).toBeEnabled();
});
