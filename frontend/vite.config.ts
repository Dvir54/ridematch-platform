/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// envDir: '..' — the repo root holds the single shared .env for every session.
// Only VITE_* variables reach the browser.
export default defineConfig({
  envDir: '..',
  plugins: [react(), tailwindcss()],
  server: { port: 5173, strictPort: true },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: true,
    restoreMocks: true,
    // Screen tests drive a debounced combobox through MSW; 5s is not enough
    // headroom when 17 files run in parallel on a cold worker.
    testTimeout: 15_000,
    // Address autocomplete is only rendered when a token exists, so the suite
    // pins its own instead of depending on whatever the local .env holds.
    env: { VITE_MAPBOX_TOKEN: 'pk.test-token' },
  },
})
