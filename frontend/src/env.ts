/**
 * Every browser-visible setting, read once. Vite's `envDir: '..'` points at the
 * repo root, so these come from the same shared .env the backend uses.
 */
export const env = {
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1',
  wsUrl: import.meta.env.VITE_WS_URL ?? 'ws://localhost:8000/api/v1/ws',
  clerkPublishableKey: import.meta.env.VITE_CLERK_PUBLISHABLE_KEY ?? '',
  mapboxToken: import.meta.env.VITE_MAPBOX_TOKEN ?? '',
  useMocks:
    import.meta.env.VITE_USE_MOCKS === 'true' || import.meta.env.MODE === 'mock',
} as const
