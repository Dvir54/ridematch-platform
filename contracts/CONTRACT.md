# RideMatch — Contract

Everything the backend, the frontend and the tests must agree on. `openapi.yaml` defines the shapes; this file defines the **rules** behind them.
If the two disagree, `openapi.yaml` wins for shapes and this file wins for behavior. Either way, a mismatch is a bug in one of them.

| File | What it defines |
|---|---|
| `openapi.yaml` | Every endpoint, request/response schema, error response |
| `schema.sql` | Table shapes, constraints, indexes, as a **reference**. The Alembic migration chain (`backend/alembic/versions`) is what defines every real database, tests included; a test keeps this file identical to it |
| `CONTRACT.md` | Conventions, state machines, business rules, matching formula, WS protocol, error codes |
| `../.env.example` | Every config variable |

---

## 1. Change process

- Every contract change: bump `info.version` in `openapi.yaml` (patch = additive, minor = breaking) and commit it **on its own** (`contract: …`).
- In the same change, keep the backend, the frontend types (`npm run gen:api`) and the tests in step.
- Never "fix" the contract silently in your own code. If the implementation can't match it, change the contract first.

## 2. Conventions

- **Base path:** `/api/v1`. WebSocket at `/api/v1/ws`.
- **Versioning:** there's only v1. `/v2` is added only for a breaking change once clients exist that you can't update in lockstep. Additive changes (new endpoints, new optional fields) stay in v1. With a domain, the prefix stays the same: `https://api.<domain>/api/v1` (or `https://<domain>/api/v1` when the frontend is served from the same origin).
- **Redis** is used only for the WebSocket connection registry (refresh tokens are gone with Clerk). Nothing depends on it to function: `/ready` reports it but isn't gated by it.
- **Request size:** a request body over 64 KiB is refused with 413 `PAYLOAD_TOO_LARGE` before any handler runs. Every legitimate body is far smaller.
- **Auth: Clerk.** Clerk owns sign-up, sign-in, sign-out, passwords, email verification, "Sign in with Google" and MFA. RideMatch has **no** register/login/refresh/logout/password endpoints and never stores passwords.
  - **Frontend:** wraps the app in Clerk's provider and uses its `<SignIn/>`, `<SignUp/>` and `<UserProfile/>` components. Before every API call it takes a fresh token from `getToken()` and sends `Authorization: Bearer <clerk_session_token>`. Clerk refreshes the token automatically, so there's no refresh flow to build.
  - **Backend:** on every request except `/health`, `/ready` and `/webhooks/clerk`, it verifies the token as RS256, against Clerk's JWKS (`CLERK_JWKS_URL`, cached) or, if `CLERK_JWT_KEY` is set, against that PEM public key with no network call. It checks `exp`/`nbf` (with 5s leeway), `iss == CLERK_ISSUER`, and `azp` ∈ `CLERK_AUTHORIZED_PARTIES`. Any failure → 401 `UNAUTHENTICATED`.
  - **Production configuration fails fast:** with `APP_ENV=production` the backend refuses to start unless `CLERK_ISSUER` (https, not a `*.clerk.accounts.dev` development instance), `CLERK_JWT_KEY` (a parseable RSA public key, so production verifies with no network call), `CLERK_AUTHORIZED_PARTIES` and `CORS_ORIGINS` (https, not localhost), `CLERK_SECRET_KEY` (`sk_live_…`) and `CLERK_WEBHOOK_SIGNING_SECRET` (`whsec_…`) are all valid, and `ADMIN_EMAIL` is empty. Every problem is reported at once.
  - **Claims used:** `sub` = Clerk user id (→ `users.clerk_user_id`), and `email` = primary email. `email` is a **custom claim**: in the Clerk Dashboard → Sessions → Customize session token, add `{"email": "{{user.primary_email_address}}"}`.
  - **User lookup:** by `clerk_user_id`. No row → 403 `ONBOARDING_REQUIRED` (except on `POST /users/me/onboarding`). A row with `is_active=false` → 403 `ACCOUNT_DEACTIVATED`.
  - Because the user lookup runs on every authenticated request, **any** authenticated endpoint can answer 403 `ONBOARDING_REQUIRED` or `ACCOUNT_DEACTIVATED`. `openapi.yaml` documents a 403 on all of them; only `/health`, `/ready` and `/webhooks/clerk` (all `security: []`) can't.
  - **Admin** is `users.is_admin` in **our** DB, not in Clerk. It's read from the DB on each request, so a change applies immediately.
  - **Sign-up flow:** Clerk sign-up → frontend calls `GET /users/me` → 403 `ONBOARDING_REQUIRED` → frontend shows the onboarding form (name, DOB, gender, ToS) → `POST /users/me/onboarding` → 201 → Role Selection.
  - **Webhooks** (`POST /webhooks/clerk`) are only for keeping data in sync later (email change, account deleted). Onboarding never waits on them, because they are async and can be delayed, repeated or out of order.
  - **Tests** never call Clerk. With `APP_ENV=test`, the test suite generates its own RSA key pair, sets `CLERK_JWT_KEY` to the public key, and signs tokens with the private key using the same claims (`sub`, `email`, `azp`, `iss`, `exp`, `nbf`). The backend has no test-only bypass: the code path is identical, only the key differs.
- **IDs:** integers.
- **Timestamps:** ISO 8601. The server always returns UTC with `Z` at **second** resolution (microseconds are dropped), and accepts any offset; a naive datetime is read as UTC.
- **Money:** decimal **string**, e.g. `"25.50"`. Never a float — a JSON number in a request body is a 422 `VALIDATION_ERROR`, since that's what typing it as a string is for. On the way in, 1 or 2 decimal places or none (`"25"`, `"25.5"` and `"25.50"` are all fine); on the way out, always 2.
- **Emails:** lowercased and trimmed by the server before storing or looking up.
- **Lists:** plain JSON arrays with `limit` (default 20, max 100) and `offset`. Admin lists also return an `X-Total-Count` header.
- **Status filters:** comma-separated, e.g. `?status=upcoming,full`. An unknown value is a 422 `VALIDATION_ERROR` with `details[].field = "query.status"`, the same answer a single-value enum parameter gives. Repeats are ignored, and an empty value (`?status=`, or one that is all commas) means **no filter** rather than an error — it's what a filter UI sends with nothing selected.
- **Non-nullable fields:** a property `openapi.yaml` does not give a `"null"` type may be **absent** from a `PATCH` body — that means "leave it alone" — but sending it as `null` is a 422 `VALIDATION_ERROR`. `details[].field` names the field itself (`body.start_lat`, `body.preferences.pets`), never just `body`. The nullable ones are `notes` on a ride, `gender` and `vehicle` on a user, and `preferences.default_mode`.
- **Every 422 carries `details`**, whatever its `code` — the specific ones (`UNDERAGE`, `TERMS_NOT_ACCEPTED`, `DEPARTURE_IN_PAST`) as much as `VALIDATION_ERROR` — with at least one entry. A client can rely on having somewhere to put the message: `code` gives the sentence, `field` the place. A failure that belongs to the body as a whole rather than one field says `body`.
- **`details` is for display, not branching.** `details[].field` names the most specific location the server can attribute a 422 to, and a later version may make it **more** specific without that counting as breaking — `body` becoming `body.start_lat` is a fix, not a break. So: branch on `code`, use `field` to highlight an input, and always keep a fallback for a `field` you can't map onto one (a coordinate inside an address picker, a key inside a nested object). A client whose only path to showing *something* is a coarse `field` will go silent the moment the server gets more precise (2026-10-02, after exactly that near-miss on the Edit Ride form).
- **Errors:** always `{ "code": "...", "message": "...", "details"?: [...] }`. The backend overrides FastAPI's default `{"detail": ...}` and its 422 format to match. Clients branch on `code`, never on `message`.
- **Not found vs forbidden:** a resource that exists but isn't yours → 403. One that doesn't exist → 404.
- **CORS:** allowed origins come from `CORS_ORIGINS`.

## 3. State machines

### Ride
```
upcoming ──(seats hit 0)──▶ full ──(seats freed by capacity edit)──▶ upcoming
upcoming | full ──start──▶ in_progress ──complete──▶ completed
upcoming | full ──cancel (driver)──▶ cancelled
upcoming | full | in_progress ──force-cancel (admin)──▶ cancelled
```
- `completed` and `cancelled` are terminal. Any other transition → 409 `INVALID_STATE_TRANSITION`.
- **Start:** driver only, allowed from `departure_time − 2h` onward (earlier → 409 `TOO_EARLY_TO_START`). Pending requests are auto-rejected (with notification).
- **Auto-complete:** a background job completes rides still `in_progress` 12h after `departure_time`.
- **Stale rides:** rides still `upcoming`/`full` 12h after `departure_time` are auto-cancelled, and pending requests auto-rejected.

### Ride request
```
pending ──approve (driver)──▶ approved
pending ──reject (driver)──▶ rejected
pending ──cancel (passenger, before ride starts)──▶ cancelled
approved ──cancel (passenger, until departure − 1h)──▶ cancelled
pending | approved ──ride cancelled──▶ cancelled
pending ──ride started / stale──▶ rejected
```
- A passenger can cancel an `approved` request until `departure_time − 1h`; after that → 409 `TOO_LATE_TO_CANCEL`. Seats return to the ride (`full` → `upcoming`), and the driver gets `request_cancelled`.
- `responded_at` is set on every transition out of `pending`.

## 4. Business rules

**Rides**
- `available_seats = capacity − SUM(seats_requested of approved requests)` must hold at all times.
- **Approve** runs in one transaction: `SELECT … FOR UPDATE` on the ride, check `available_seats ≥ seats_requested` (else 409 `NOT_ENOUGH_SEATS`), decrement, set `full` at 0, update the request, create the notification. The WS push/email happens **after commit**.
- **Edit** (`PATCH`): only in `upcoming`/`full`. With ≥1 approved request, changes to any location field or `departure_time` → 409 `RIDE_HAS_APPROVED_PASSENGERS`, and `capacity` below the approved seats → 409 `CAPACITY_BELOW_APPROVED`. Price/notes/preferences are always editable.
- **Preferences on `PATCH`** shallow-merge, exactly like user preferences: an absent key is left alone, and all four keys (`smoking`, `pets`, `music`, `gender_only`) behave the same way. So the Edit Ride form may send only what changed. Reads (`Ride.preferences`) always come back complete, with the server's defaults filled; writes use `RidePreferencesPatch`, which has none. Booleans must be real JSON booleans.
- **Cancel** is allowed even with approved passengers (they're notified). The original design's "edit or cancel only without approved passengers" is read as applying to *edit*, because `cancel_ride` explicitly notifies approved passengers. Every pending and approved request becomes `cancelled`, so `available_seats` goes back to `capacity` and the invariant above still holds.
- A locked field counts as a **change** when the key is present, even if the value is identical — the server compares what was sent, not what it means. And a `departure_time` sent on `PATCH` must still be in the future (422 `DEPARTURE_IN_PAST`), exactly as on create.

**Requests**
- A passenger can't request their own ride (409 `CANNOT_REQUEST_OWN_RIDE`).
- `Ride.my_request` carries the caller's own blocking request on that ride (`{id, status, seats_requested}`), or `null`. It is the single pending/approved/rejected row the partial unique index allows, so there is never more than one and no "latest" to pick; a cancelled row reads as `null`, which is exactly D2 — the request button comes back. It is `null` for a driver on their own ride, and it is filled by that one rule everywhere, **including** the ride embedded in a `RideRequest`, where it is the caller's *current* request on that ride and so may differ from the row being held. In request lists read the outer `RideRequest`; `my_request` exists for Ride Details and search result cards, which have no outer request to read.
- Only rides with `status=upcoming` accept requests (409 `RIDE_NOT_OPEN`). `seats_requested ≤ available_seats` at request time (409 `NOT_ENOUGH_SEATS`), re-checked at approval.
- At most one pending/approved request per (ride, passenger) (409 `REQUEST_ALREADY_EXISTS`).
- If the driver rejected the passenger on this ride, they can't request it again (409 `PREVIOUSLY_REJECTED`). After the passenger's **own** cancel, re-requesting is allowed (seats permitting).
- Auto-rejections (ride started / stale) don't matter here, since the ride is no longer open anyway.
- The 409s on `POST /rides/{id}/requests` are checked in the order `openapi.yaml` lists them: own ride, ride not open, seats, active request, previously rejected. So a passenger who already has a pending request and asks for more seats than are free gets `NOT_ENOUGH_SEATS`, not `REQUEST_ALREADY_EXISTS`.
- **Cancelling** a request needs the ride itself to still be `upcoming`/`full`. On an `in_progress` or finished ride it's `INVALID_STATE_TRANSITION`, not `TOO_LATE_TO_CANCEL` — the cutoff only decides between a seat the passenger may still give back and one they may not. At exactly `departure_time − 1h` the cancel is still allowed.
- **Approving** needs the ride `upcoming`/`full`: `in_progress` or terminal is `INVALID_STATE_TRANSITION`, while a `full` ride has no free seat and so answers `NOT_ENOUGH_SEATS`.

**Vehicles**
- `users.vehicle = {make, model, color, plate}`. It's set at onboarding (optional) or with `PATCH /users/me` (full replace).
- It's required to create a ride (409 `VEHICLE_REQUIRED`). It can't be removed while the user has `upcoming`/`full` rides (409 `VEHICLE_REQUIRED`).
- Make/model/color are public (`UserPublic.vehicle`). The plate is private: it appears only in `Ride.driver_vehicle_plate`, and only for the driver and passengers with an approved request on that ride.

**Ratings**
- Only on `completed` rides (409 `RIDE_NOT_COMPLETED`).
- Participants = the driver + passengers with an **approved** request. The driver rates passengers (`role_rated=passenger`) and passengers rate the driver (`role_rated=driver`). Anything else → 403 `NOT_A_PARTICIPANT`.
- One per direction per ride (409 `ALREADY_RATED`).
- Cached average update, in the same transaction: `new = (old * count + score) / (count + 1)`, `count += 1`.
- The cached average is stored as a `double precision` and is **not** rounded on write; clients round for display.
- `GET /ratings/pending` lists one entry per counterpart the caller still owes a rating on a completed ride — for a driver, every approved passenger; for an approved passenger, the driver. See D21 for the window and the order.
- A rating writes a `rating_received` notification for the ratee (no email), pushed after commit like every other notification.

**Users**
- 18+ at onboarding (422 `UNDERAGE`). `accepted_terms` must be `true` (422 `TERMS_NOT_ACCEPTED`), and `terms_accepted_at` is stored.
- **Admins in production** are granted only by the CLI, run on the server: `python -m app.admin_cli grant <email>` (and `revoke <email>`). It refuses an unknown or deactivated user, is idempotent, and exits non-zero on failure. Nothing promotes a user automatically in production.
- **Development and test only:** if the onboarding email equals `ADMIN_EMAIL` **and no admin exists yet**, the user is created with `is_admin=true`. With `APP_ENV=production` this path is off, and the backend refuses to start if `ADMIN_EMAIL` is set. Clerk must still require a verified email at sign-up, since email identity also drives `EMAIL_ALREADY_EXISTS`.
- Password and email changes happen in Clerk. Webhook `user.updated` updates `users.email`. Webhook `user.deleted` (and `python -m app.admin_cli anonymise <email>` for a deletion request made outside Clerk) sets `is_active=false`, closes the user's sockets and **anonymises** the profile: `name` → `Deleted user`, `email` → `deleted-<id>@deleted.invalid`, `clerk_user_id` → `deleted_<id>`, `gender`, `vehicle` and `preferences` → null, `date_of_birth` → `1900-01-01` (the column is NOT NULL; the 18+ check already happened at onboarding). Rides, requests and ratings stay, so the other party's history is intact; their free text (ride notes, rating comments) is kept as written.
- Admin deactivate → `is_active=false` + ban the user through Clerk's Backend API (`CLERK_SECRET_KEY`), which ends their sessions. Reactivate → unban. If the Clerk call fails, the DB change still applies (it's enforced anyway) and the failure is logged.
- `last_login_at` is updated on an authenticated request when it's older than 1 hour. It feeds `active_users` in analytics.
- RideMatch does **not** collect a phone number (removed in 0.5.0, D22). A `phone` key in a request body is ignored like any other unknown key.
- `preferences` read → the server fills defaults for missing keys (`UserPreferences`). Writes use `UserPreferencesPatch`, which carries no defaults: `PATCH` and onboarding shallow-merge what is sent (the `notifications` sub-object is merged too), an absent key is left alone, and `default_mode: null` clears it. Booleans must be real JSON booleans — `"yes"` is a 422.

## 5. Error codes

| HTTP | code | When |
|---|---|---|
| 400 | `INVALID_WEBHOOK_SIGNATURE` | Clerk webhook with a missing or bad Svix signature |
| 400 | `BAD_REQUEST` | a request body that isn't parseable JSON (a well-formed body that fails validation is a 422) |
| 401 | `UNAUTHENTICATED` | missing, invalid or expired Clerk session token |
| 403 | `ONBOARDING_REQUIRED` | valid Clerk user, but no RideMatch profile yet |
| 403 | `ACCOUNT_DEACTIVATED` | `is_active=false` |
| 403 | `FORBIDDEN` | not the owner / not admin |
| 403 | `NOT_A_PARTICIPANT` | rating someone you didn't ride with in the allowed direction |
| 404 | `NOT_FOUND` | resource doesn't exist |
| 409 | `ALREADY_ONBOARDED` | onboarding called twice |
| 409 | `EMAIL_ALREADY_EXISTS` | onboarding with an email another profile already uses |
| 409 | `INVALID_STATE_TRANSITION` | action not allowed from the current status |
| 409 | `TOO_EARLY_TO_START` | start before `departure_time − 2h` |
| 409 | `RIDE_HAS_APPROVED_PASSENGERS` | editing locked fields |
| 409 | `CAPACITY_BELOW_APPROVED` | capacity < approved seats |
| 409 | `CANNOT_REQUEST_OWN_RIDE` | driver requests own ride |
| 409 | `RIDE_NOT_OPEN` | request on a non-`upcoming` ride |
| 409 | `NOT_ENOUGH_SEATS` | seats unavailable (request or approve) |
| 409 | `REQUEST_ALREADY_EXISTS` | duplicate active request |
| 409 | `PREVIOUSLY_REJECTED` | driver already rejected this passenger on this ride |
| 409 | `TOO_LATE_TO_CANCEL` | passenger cancels an approved seat less than 1h before departure |
| 409 | `VEHICLE_REQUIRED` | offering a ride without a vehicle, or removing it while rides are open |
| 409 | `RIDE_NOT_COMPLETED` | rating before completion |
| 409 | `ALREADY_RATED` | duplicate rating |
| 409 | `CANNOT_DEACTIVATE_SELF` | admin deactivating self |
| 413 | `PAYLOAD_TOO_LARGE` | request body over 64 KiB, on any endpoint |
| 422 | `VALIDATION_ERROR` | schema validation; `details` lists fields |
| 422 | `UNDERAGE` / `TERMS_NOT_ACCEPTED` / `DEPARTURE_IN_PAST` | specific validation failures |
| 503 | `NOT_READY` | `GET /ready` only: the database is unreachable |

## 6. WebSocket protocol

- Connect: `GET /api/v1/ws` with **no token in the URL** (URLs end up in access and proxy logs). The page's `Origin` must be one of `CORS_ORIGINS`, or the server closes with **4403**.
- Authenticate: the client's **first message** must be `{"event": "auth", "token": "<clerk_session_token>"}`, with a fresh token from `getToken()`, within **10 seconds** of connecting. The server answers `{"event": "ready"}` and only then registers the socket. An invalid or expired token, no profile, any other first message, or no `auth` within 10 s → the server closes with code **4401**; a deactivated account → **4403**. On 4401, the client gets a new token and reconnects with backoff. A `token` query parameter is ignored.
- Frames are capped at 64 KiB.
- The server registers the connection in Redis (`ws:online:{user_id}`, a counter, since there can be several tabs).
- Server → client: `{"event": "notification", "data": <Notification>}`, the exact same object `GET /notifications` returns.
- Client → server: `{"event": "ping"}` every 25s. The server replies `{"event": "pong"}`. With no ping for 60s, the server closes the socket.
- The server pushes only if the user's `preferences.notifications.websocket` is not `false`. The DB row is written regardless.
- The token is only checked at connect (Clerk tokens expire in about a minute), so an open socket is **not** closed when its token expires. Deactivating a user closes their open sockets.

## 7. Notifications & matching

### Notification triggers

| Event | Recipient(s) | type | Email |
|---|---|---|---|
| Onboarding completed | new user | `welcome` | ✅ |
| Request created | driver | `request_created` | |
| Request approved | passenger | `request_approved` | ✅ (ride confirmation) |
| Request rejected (incl. auto) | passenger | `request_rejected` | ✅ |
| Request cancelled by passenger (pending or approved) | driver | `request_cancelled` | |
| Ride cancelled (driver/admin/stale) | pending + approved passengers (+ driver if admin) | `ride_cancelled` | |
| 1h before departure (job, every minute) | driver + approved passengers | `ride_reminder` | |
| Ride started | approved passengers | `ride_started` | |
| Ride completed | driver + approved passengers | `ride_completed` (prompts rating) | |
| Rating received | ratee | `rating_received` | |

Email goes through `notifications_service.send_email`. `EMAIL_BACKEND=console` logs instead of sending (default in dev and tests). Background jobs (reminders, auto-complete, stale rides) run as an in-process asyncio loop started on app startup.

### Matching formula (`/search`)
**Candidates:** `status=upcoming`, `available_seats ≥ seats`, `departure_time > now()`, `|departure_time − time| ≤ 4h`, pickup and dropoff distance ≤ `SEARCH_RADIUS_KM` (default 10), not the caller's own ride, no pending/approved request by the caller. A `gender_only` ride is **excluded** unless the caller's gender is set and equals the driver's.

Let `R = SEARCH_RADIUS_KM`, `p = haversine(passenger start, ride start)`, `d = haversine(passenger end, ride end)`, `Δ = |departure_time − time|` in hours.

| Component | Max | Formula |
|---|---|---|
| route | 40 | `20·max(0, 1 − p/R) + 20·max(0, 1 − d/R)` |
| time | 25 | `Δ ≤ 2` → 25; `2 < Δ ≤ 4` → `25·(4 − Δ)/2`; else 0 |
| price | 15 | no budget or `price ≤ budget` → 15; else `15·max(0, 1 − (price − budget)/budget)` (budget 0 → 0) |
| rating | 10 | no rating → 5; `≥ 4.5` → 10; else `10·(rating − 1)/3.5` |
| preferences | 10 | start at 10; −5 if the ride allows smoking and the passenger's `smoking=false`; −5 if the ride allows pets and the passenger's `pets=false`; min 0 |

`match_score` = the sum, rounded to 1 decimal. Keep only `≥ MATCH_MIN_SCORE` (40). Sort: `best_match` = score desc, then departure asc; `earliest` = departure asc; `cheapest` = price asc, then score desc. Earth radius = 6371 km.

## 8. Decisions (D1–D15 approved 2026-09-30; later rows carry their own date)

| # | Decision | Why |
|---|---|---|
| D1 | Approving deducts `seats_requested`, not always 1 | The doc says `-= 1`, but the table has `seats_requested` |
| D2 | Re-request allowed only after the passenger's own cancel; a driver's reject is final for that ride | A plain `UNIQUE(ride_id, passenger_id)` blocks re-requesting forever; allowing it after reject would let a passenger spam the driver |
| D3 | Drivers can cancel a ride that has approved passengers | The doc contradicts itself; `cancel_ride` notifies approved passengers |
| D4 | `gender_only` hard filter = the passenger's gender must equal the driver's | The doc doesn't define it |
| D5 | Matching formulas in §7 | The doc gives only point ranges |
| D6 | **Auth moved to Clerk.** The `/auth/*` endpoints, `password_hash`, email-verification columns and Redis refresh tokens are removed | Your choice. Clerk also covers email verification and social login |
| D7 | Start allowed from `departure − 2h`; auto-complete/stale after 12h | The doc says "on departure day" and "auto/manually" |
| D8 | `date_of_birth` required at onboarding (NOT NULL in DB) | 18+ can't be enforced otherwise, and Clerk doesn't collect DOB |
| D9 | Added endpoints: `/users/me/stats`, `/requests/incoming`, `/ratings/pending`, `/notifications/unread-count` | Needed by the Home, Requests and rating-prompt screens |
| D10 | Base path `/api/v1` | Lets the built frontend be served from the same origin later |
| D11 | A profile row is created only at onboarding (not from the webhook, not lazily on first request) | No half-empty users; no dependence on webhook timing |
| D12 | `is_admin` lives in our DB, not in Clerk metadata | One source of truth, applies instantly, and is testable without Clerk |
| D13 | Tests sign their own tokens with a local key via `CLERK_JWT_KEY` | Tests run offline and fast, with no auth bypass in the code |
| D14 | Vehicle info in v1 (`users.vehicle`); plate only visible to the driver and approved passengers | Passengers need to find the car; the plate is private |
| D15 | Approved passengers can cancel until 1h before departure | Plans change; the cutoff protects the driver from last-minute no-shows |
| D16 | **Ride preferences on `PATCH` shallow-merge**, absent keys left alone — same rule as user preferences (2026-10-01) | Raised by the frontend: the Edit Ride form has to know whether a partial object wipes the rest. One merge rule for both kinds of preferences is less to remember |
| D17 | **The `Phone` format applies to `PATCH /users/me`, not just onboarding** (2026-10-01). Breaking: a loose phone that used to be accepted is now 422 | The tests and the frontend both flagged the inconsistency. One `Phone` schema is now shared by both request bodies so they can't drift |
| D18 | **`Phone` widened to allow parentheses and dots** (2026-10-01), so `+1 (555) 010-9999` is valid. Additive — nothing that was accepted became invalid | The tests and the frontend independently called parenthesised numbers a natural thing to type. Cheaper to widen before the profile editor is built against the strict rule |
| D20 | **`Ride.my_request` added** (2026-10-01): `{id, status, seats_requested} | null`, the caller's own blocking request on that ride. Additive. §7 is deliberately **unchanged** — a previously-rejected ride stays a search candidate | The frontend was reading `/requests/mine?limit=100` and scanning it to decide what the passenger Ride Details screen should offer, which silently breaks past 100 closed requests. A status alone wouldn't do: cancelling needs the request **id**, so the object carries it. It also lets a search card show a ride the driver already refused as refused, instead of offering a button whose only answer is `PREVIOUSLY_REJECTED` — the backend and the frontend both preferred showing it greyed out with a reason over making it vanish, hence §7 standing pat |
| D19 | **The Phase 2 edge cases are now written down** (2026-10-01): the 409 order on creating a request, `available_seats` returning to `capacity` when a ride is cancelled, a locked field counting as a change by presence, `DEPARTURE_IN_PAST` applying to `PATCH` too, `INVALID_STATE_TRANSITION` (not `TOO_LATE_TO_CANCEL`) once the ride has started, `NOT_ENOUGH_SEATS` when approving on a `full` ride, and an unknown `status` filter being a 422. Each one was undefined before, so nothing documented changed meaning | Writing the ride loop turned up seven places where two readings were equally defensible. the tests have to assert exactly one of them, so the contract now says which |

| D21 | **Phase 5 semantics written down** (2026-10-02). `/users/me/stats` — as_driver: `rides_offered` = every ride the user ever created (any status, cancelled included); `rides_completed` = their rides with `status=completed`; `upcoming_rides` = their `upcoming` + `full` rides; `pending_requests` = pending requests across all their rides; `passengers_carried` = sum of `seats_requested` over approved requests on their **completed** rides. as_passenger: `trips_requested` = every request the user ever made (any status); `trips_completed` = their **approved** requests on `completed` rides; `upcoming_trips` = their **approved** requests on `upcoming`/`full` rides. "Upcoming" therefore means the same thing on both sides, and an `in_progress` ride counts in neither the upcoming nor the completed counter. `/ratings/pending` lists only completed rides whose `departure_time` is within the last 30 days, ordered by `departure_time` descending, then `to_user.id` ascending. `POST /ratings` checks in this order: ride 404, `to_user` 404, 409 `RIDE_NOT_COMPLETED`, 403 `NOT_A_PARTICIPANT` (self-rating and passenger-rating-passenger included), 409 `ALREADY_RATED`; its `rating_received` notification points at the **ride** (`related_entity_type="ride"`), since `rating` is not one of the two values the column allows. Additive — nothing documented changed meaning | Every counter had two defensible readings (does a cancelled ride count as offered? is a started trip still upcoming?), and the tests have to assert exactly one |
| D22 | **0.5.0 production hardening** (2026-10-03). Breaking: WebSocket auth moved from `?token=` to a first `auth` message, with an `Origin` check and a `ready` reply; `/health` became pure liveness (`{"status": "ok"}`) and the DB check moved to the new `/ready` (503 `NOT_READY`); the phone number was removed from onboarding, `PATCH /users/me` and every user object. Additive: 413 `PAYLOAD_TOO_LARGE`; production admins via `app.admin_cli` (the `ADMIN_EMAIL` bootstrap is development-only); `user.deleted` anonymises the profile | Tokens must not appear in URLs/logs; host health checks need a readiness signal that fails when the DB does; the phone was collected but used by nothing; no unverified or unintended user may become admin by signing up first; deleting an account must remove its personal data |

## 9. Scope — what's in v1 and what's later (decided 2026-09-30)

| # | Item | Scope | Notes |
|---|---|---|---|
| G1 | Vehicle info | **v1** | See §4 Vehicles, D14 |
| G2 | Payment methods | later | Hide from the Profile screen. Payment is off-app (cash/Bit); price is informational |
| G3 | Phone number | removed | Not collected (D22) |
| G4 | Avg match score in analytics | later | Removed from `AnalyticsSummary`. Would need `match_score` stored on `ride_requests` |
| G5a | Address autocomplete (address → lat/lng) | **v1** | Frontend only, **Mapbox** Search/Geocoding. Sends `*_address` + `*_lat/lng` exactly as the contract says; the backend doesn't call Mapbox |
| G5b | Map / route preview | later | Search results "map toggle" and Create Ride "route preview" are hidden in v1 |
| G6 | Web push notifications | later | WebSocket + email only. `preferences.notifications.push` is stored but unused |
| G7 | Approved passenger cancels | **v1** | Until 1h before departure — see §3, D15 |
| — | Email verification | done | Clerk (required at sign-up) |
