import { expect, test } from '@playwright/test';

// Proves Cross-Origin-Resource-Policy: same-origin on the API (see
// backend/app/security/headers.py) does not break the front end's real
// cross-origin calls to it. Unlike backend-down.spec.ts, nothing here is
// mocked or route-intercepted: every request goes to the actual running
// backend, so a CORP (or CORS) misconfiguration would show up as a real
// failed response, not a simulated one.
//
// Run against both serving modes by hand when changing this header, since
// the two use different ports and Playwright's webServer config only
// drives one at a time:
//   npm run dev      (port 5173) -- what this spec runs against via `npm run test:e2e`
//   npm run preview  (port 4173) -- build first; also re-run this file with
//                      `--project=chromium` and FRONTEND_ORIGIN=http://localhost:4173
//                      set on the backend, or just repeat the three checks by hand.
test('health, model-info and score calls to the live backend all succeed', async ({ page }) => {
  const healthResponse = page.waitForResponse((r) => r.url().endsWith('/api/v1/health'));
  await page.goto('/');
  expect((await healthResponse).status()).toBe(200);

  const modelInfoResponse = page.waitForResponse((r) => r.url().endsWith('/api/v1/model-info'));
  await page.goto('/about');
  expect((await modelInfoResponse).status()).toBe(200);

  await page.goto('/');
  await page.getByRole('button', { name: 'Use sample text' }).click();
  const scoreResponse = page.waitForResponse((r) => r.url().endsWith('/api/v1/score'));
  await page.getByRole('button', { name: 'Analyse text' }).click();
  expect((await scoreResponse).status()).toBe(200);

  // The verdict card rendering confirms the response body was actually
  // readable by the page's JS, not just that a 200 crossed the wire.
  await expect(page.getByRole('region', { name: 'Analysis result' })).toBeVisible();
});
