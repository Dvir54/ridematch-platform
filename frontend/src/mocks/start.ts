import { env } from '../env'

/**
 * No-ops unless VITE_USE_MOCKS=true (or `npm run dev:mock`). The first check is
 * static, so a production build drops the whole MSW chunk.
 */
export async function startMocks(): Promise<void> {
  if (!(import.meta.env.DEV || import.meta.env.MODE === 'mock')) return
  if (!env.useMocks) return
  const { worker } = await import('./browser')
  await worker.start({
    onUnhandledRequest: 'bypass',
    serviceWorker: { url: `${import.meta.env.BASE_URL}mockServiceWorker.js` },
  })
}
