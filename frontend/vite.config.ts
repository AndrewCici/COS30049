import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The backend origin this app calls (api.ts defaults VITE_API_BASE to the
// same value); kept in sync with it here so connect-src is never stricter
// than what the app actually needs to reach.
const API_ORIGIN = 'http://localhost:8000'

// Mirrors the backend's security headers (see backend/app/security/headers.py)
// for the pages Vite itself serves. style-src needs 'unsafe-inline' because
// MUI's emotion engine injects <style> tags at runtime with no nonce.
//
// Dev mode needs three further allowances the production build (vite
// preview) does not: 'unsafe-eval' for Vite's HMR client; 'unsafe-inline'
// on script-src because @vitejs/plugin-react injects an un-nonced inline
// <script type="module"> bootstrap into index.html to wire up React Fast
// Refresh (confirmed by hand -- without it the page never renders, failing
// with "can't detect preamble"); and a websocket back to this same origin,
// which carries the HMR protocol itself.
const SECURITY_HEADERS = {
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'no-referrer',
  'X-Frame-Options': 'DENY',
  'Permissions-Policy': 'geolocation=(), camera=(), microphone=(), payment=()',
}

function csp(dev: boolean): string {
  const scriptSrc = dev ? "'self' 'unsafe-eval' 'unsafe-inline'" : "'self'"
  const connectSrc = dev ? `'self' ${API_ORIGIN} ws://localhost:5173` : `'self' ${API_ORIGIN}`
  return [
    "default-src 'self'",
    `script-src ${scriptSrc}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "font-src 'self'",
    `connect-src ${connectSrc}`,
    "frame-ancestors 'none'",
  ].join('; ')
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Fixed port (never auto-bump to 5174+) so the backend's CORS
    // allow-list (FRONTEND_ORIGIN) always matches where this actually runs.
    port: 5173,
    strictPort: true,
    headers: { ...SECURITY_HEADERS, 'Content-Security-Policy': csp(true) },
  },
  preview: {
    port: 4173,
    headers: { ...SECURITY_HEADERS, 'Content-Security-Policy': csp(false) },
  },
})
