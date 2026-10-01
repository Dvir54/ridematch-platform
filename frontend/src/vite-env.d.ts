/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Backend base URL including the /api/v1 prefix. */
  readonly VITE_API_BASE_URL?: string
  /** WebSocket endpoint (used from Phase 4). */
  readonly VITE_WS_URL?: string
  readonly VITE_CLERK_PUBLISHABLE_KEY?: string
  readonly VITE_MAPBOX_TOKEN?: string
  /** "true" serves the API from MSW instead of the backend. `npm run dev:mock` also turns it on. */
  readonly VITE_USE_MOCKS?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
