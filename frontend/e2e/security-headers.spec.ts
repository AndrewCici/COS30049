import { expect, test } from '@playwright/test';

test('the served page carries the security headers configured in vite.config.ts', async ({ page }) => {
  const response = await page.goto('/');
  expect(response).not.toBeNull();
  const headers = response!.headers();

  expect(headers['x-content-type-options']).toBe('nosniff');
  expect(headers['referrer-policy']).toBe('no-referrer');
  expect(headers['x-frame-options']).toBe('DENY');
  expect(headers['cross-origin-resource-policy']).toBe('same-origin');
  expect(headers['cross-origin-opener-policy']).toBe('same-origin');

  const csp = headers['content-security-policy'] ?? '';
  expect(csp).toContain("base-uri 'self'");
  expect(csp).toContain("form-action 'self'");
  expect(csp).toContain("frame-ancestors 'none'");
});
