import { expect, test } from '@playwright/test';

test('an unknown route shows the 404 page with a way home', async ({ page }) => {
  await page.goto('/this-route-does-not-exist');

  await expect(page.getByRole('heading', { name: 'Page not found' })).toBeVisible();
  await page.getByRole('link', { name: 'Back to the detector' }).click();
  await expect(page).toHaveURL('/');
});
