import { expect, test } from '@playwright/test';

test('a render error is caught by the root ErrorBoundary instead of a blank page', async ({ page }) => {
  // The ?crash=1 trigger in DetectorPage only throws when import.meta.env.DEV
  // is true, i.e. under `vite`/`vite dev`, which is what webServer runs here.
  await page.goto('/?crash=1');

  await expect(page.getByRole('heading', { name: 'Something went wrong' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Reload' })).toBeVisible();
});
