import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Fixed port (never auto-bump to 5174+) so the backend's CORS
    // allow-list (FRONTEND_ORIGIN) always matches where this actually runs.
    port: 5173,
    strictPort: true,
  },
})
