# Role: @frontend

You build the React + Vite + TypeScript app in `frontend/`.

## Setup
- `npm create vite@latest` (react-ts) inside `frontend/`, TypeScript `strict`.
- `vite.config.ts`: `envDir: '..'` so it reads the shared root `.env`. Use only `VITE_*` variables.
- Libraries: React Router, TanStack Query, Clerk React SDK (check Clerk's React quickstart for the current package name and API), Mapbox Search JS (React), Tailwind CSS, MSW, Vitest + Testing Library.
- API types come **generated** from the contract, never written by hand:
  `npx openapi-typescript ../contracts/openapi.yaml -o src/api/schema.d.ts` (add it as `npm run gen:api`). Re-run it whenever @backend announces a contract change.

## Structure
```
frontend/src/
  api/        client.ts (fetch wrapper: base URL, Clerk token via getToken(), error → ApiError{code}), schema.d.ts, hooks per resource
  mocks/      MSW handlers built from the contract (on when VITE_USE_MOCKS=true)
  auth/       Clerk provider, route guards (signed-in, onboarded, admin)
  features/   onboarding/ driver/ passenger/ notifications/ ratings/ admin/ profile/
  components/ shared UI
  ws/         WebSocket client (Phase 4)
```

## Rules
- Branch on `error.code`, never on `message`. Map every code in CONTRACT §5 that a screen can hit to a clear user message.
- Flow after sign-in: `GET /users/me` → 403 `ONBOARDING_REQUIRED` → Onboarding → Role Selection (if `preferences.default_mode` is null) → home for that mode.
- Show admin UI only when `is_admin` (the backend enforces it anyway).
- Send money as strings (`"25.50"`) and datetimes as ISO with offset. Show times in the user's local zone.
- Out of scope in v1 (CONTRACT §9): payment methods, map/route preview, push notifications. Hide these.
- Build against MSW mocks until @backend sends `READY`, then switch that area to the real API and check it in the browser.

## Checks before each commit
```
cd frontend && npm run typecheck && npm run lint && npm run test -- --run && npm run build
```
(Define `typecheck` as `tsc --noEmit`.)

## Coordination
- If a contract detail is unclear or missing for a screen, message @backend with the screen, the endpoint and your question.
- When a screen works against the real API, say so in your phase summary for Dvir.
