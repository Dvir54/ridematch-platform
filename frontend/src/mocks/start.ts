import { env } from '../env'

/** No-ops unless VITE_USE_MOCKS=true (or `npm run dev:mock`). */
export async function startMocks(): Promise<void> {
  if (!env.useMocks) return
  const { worker } = await import('./browser')
  await worker.start({
    onUnhandledRequest: 'bypass',
    serviceWorker: { url: `${import.meta.env.BASE_URL}mockServiceWorker.js` },
  })
}
