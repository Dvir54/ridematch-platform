/// <reference types="vitest/config" />
import { rmSync } from 'node:fs'
import { resolve } from 'node:path'
import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

/** MSW's worker lives in public/ for dev and mock mode; a production build ships without it. */
function dropMockWorker(): Plugin {
  let outDir = 'dist'
  let production = false
  return {
    name: 'ridematch:drop-mock-worker',
    apply: 'build',
    configResolved(config) {
      outDir = resolve(config.root, config.build.outDir)
      production = config.mode === 'production'
    },
    closeBundle() {
      if (production) rmSync(resolve(outDir, 'mockServiceWorker.js'), { force: true })
    },
  }
}

// envDir: '..' — the repo root holds the single shared .env for every session.
// Only VITE_* variables reach the browser.
export default defineConfig({
  envDir: '..',
  plugins: [react(), tailwindcss(), dropMockWorker()],
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
