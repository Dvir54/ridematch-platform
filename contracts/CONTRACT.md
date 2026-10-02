# RideMatch — Contract

Everything the three sessions must agree on. `openapi.yaml` defines the shapes; this file defines the **rules** behind them.
If the two disagree, `openapi.yaml` wins for shapes and this file wins for behavior. Either way, report the mismatch to @backend.

| File | What it defines |
|---|---|
| `openapi.yaml` | Every endpoint, request/response schema, error response |
| `schema.sql` | Table shapes, constraints, indexes (reference; backend implements via SQLAlchemy + Alembic) |
| `CONTRACT.md` | Conventions, state machines, business rules, matching formula, WS protocol, error codes |
| `../.env.example` | Every config variable |

---

## 1. Ownership & change process

| Session | Owns | Branch |
|---|---|---|
| @backend | `/backend`, `/contracts` | `feat/backend` |
| @frontend | `/frontend` | `feat/frontend` |
| @tests | `/tests` | `feat/tests` |

- **Only @backend edits `/contracts`.** Others who need a change message @backend with the proposed change and the reason.
- Every contract change: bump `info.version` in `openapi.yaml` (patch = additive, minor = breaking), commit it **on its own** (`contract: …`), then message @frontend and @tests with *what changed, whether it's breaking, and the commit hash*.
- **Additive** changes don't need Dvir's approval — bump, commit, notify. **Breaking** changes do (decided 2026-10-01).
- Never "fix" the contract silently in your own code. If the implementation can't match it, raise it.

## 2. Conventions

- **Base path:** `/api/v1`. WebSocket at `/api/v1/ws`.
- **Versioning:** there's only v1. `/v2` is added only for a breaking change once clients exist that you can't update in lockstep. Additive changes (new endpoints, new optional fields) stay in v1. With a domain, the prefix stays the same: `https://api.<domain>/api/v1` (or `https://<domain>/api/v1` when the frontend is served from the same origin).
- **Redis** is used only for the WebSocket connection registry (refresh tokens are gone with Clerk).
- **Auth: Clerk.** Clerk owns sign-up, sign-in, sign-out, passwords, email verification, "Sign in with Google" and MFA. RideMatch has **no** register/login/refresh/logout/password endpoints and never stores passwords.
  - **Frontend:** wraps the app in Clerk's provider and uses its `<SignIn/>`, `<SignUp/>` and `<UserProfile/>` components. Before every API call it takes a fresh token from `getToken()` and sends `Authorization: Bearer <clerk_session_token>`. Clerk refreshes the token automatically, so there's no refresh flow to build.
  - **Backend:** on every request except `/health` and `/webhooks/clerk`, it verifies the token as RS256, against Clerk's JWKS (`CLERK_JWKS_URL`, cached) or, if `CLERK_JWT_KEY` is set, against that PEM public key with no network call. It checks `exp`/`nbf` (with 5s leeway), `iss == CLERK_ISSUER`, and `azp` ∈ `CLERK_AUTHORIZED_PARTIES`. Any failure → 401 `UNAUTHENTICATED`.
  - **Claims used:** `sub` = Clerk user id (→ `users.clerk_user_id`), and `email` = primary email. `email` is a **custom claim**: in the Clerk Dashboard → Sessions → Customize session token, add `{"email": "{{user.primary_email_address}}"}`.
  - **User lookup:** by `clerk_user_id`. No row → 403 `ONBOARDING_REQUIRED` (except on `POST /users/me/onboarding`). A row with `is_active=false` → 403 `ACCOUNT_DEACTIVATED`.
  - Because the user lookup runs on every authenticated request, **any** authenticated endpoint can answer 403 `ONBOARDING_REQUIRED` or `ACCOUNT_DEACTIVATED`. `openapi.yaml` documents a 403 on all of them; only `/health` and `/webhooks/clerk` (both `security: []`) can't.
  - **Admin** is `users.is_admin` in **our** DB, not in Clerk. It's read from the DB on each request, so a change applies immediately.
  - **Sign-up flow:** Clerk sign-up → frontend calls `GET /users/me` → 403 `ONBOARDING_REQUIRED` → frontend shows the onboarding form (name, phone, DOB, gender, ToS) → `POST /users/me/onboarding` → 201 → Role Selection.
  - **Webhooks** (`POST /webhooks/clerk`) are only for keeping data in sync later (email change, account deleted). Onboarding never waits on them, because they are async and can be delayed, repeated or out of order.
  - **Tests** never call Clerk. With `APP_ENV=test`, @tests generates its own RSA key pair, sets `CLERK_JWT_KEY` to the public key, and signs tokens with the private key using the same claims (`sub`, `email`, `azp`, `iss`, `exp`, `nbf`). The backend has no test-only bypass: the code path is identical, only the key differs.
- **IDs:** integers.
- **Timestamps:** ISO 8601. The server always returns UTC with `Z` at **second** resolution (microseconds are dropped), and accepts any offset; a naive datetime is read as UTC.
- **Money:** decimal **string**, e.g. `"25.50"`. Never a float — a JSON number in a request body is a 422 `VALIDATION_ERROR`, since that's what typing it as a string is for. On the way in, 1 or 2 decimal places or none (`"25"`, `"25.5"` and `"25.50"` are all fine); on the way out, always 2.
- **Emails:** lowercased and trimmed by the server before storing or looking up.
- **Lists:** plain JSON arrays with `limit` (default 20, max 100) and `offset`. Admin lists also return an `X-Total-Count` header.
- **Status filters:** comma-separated, e.g. `?status=upcoming,full`. An unknown value is a 422 `VALIDATION_ERROR` with `details[].field = "query.status"`, the same answer a single-value enum parameter gives. Repeats are ignored, and an empty value (`?status=`, or one that is all commas) means **no filter** rather than an error — it's what a filter UI sends with nothing selected.
- **Non-nullable fields:** a property `openapi.yaml` does not give a `"null"` type may be **absent** from a `PATCH` body — that means "leave it alone" — but sending it as `null` is a 422 `VALIDATION_ERROR`. `details[].field` names the field itself (`body.start_lat`, `body.preferences.pets`), never just `body`. The nullable ones are `notes` on a ride, `phone`, `gender` and `vehicle` on a user, and `preferences.default_mode`.
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
- **Cancel** is allowed even with approved passengers (they're notified). The design doc's "edit or cancel only without approved passengers" is read as applying to *edit*, because `cancel_ride` explicitly notifies approved passengers. Every pending and approved request becomes `cancelled`, so `available_seats` goes back to `capacity` and the invariant above still holds.
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

**Users**
- 18+ at onboarding (422 `UNDERAGE`). `accepted_terms` must be `true` (422 `TERMS_NOT_ACCEPTED`), and `terms_accepted_at` is stored.
- If the onboarding email equals `ADMIN_EMAIL` **and no admin exists yet**, the user is created with `is_admin=true`. This is only safe because Clerk requires a verified email at sign-up, so keep that setting on. That's how the first admin exists: sign up in Clerk with that email and onboard. More admins: set `is_admin` by script/SQL.
- Password and email changes happen in Clerk. Webhook `user.updated` updates `users.email`. Webhook `user.deleted` sets `is_active=false` and closes the user's sockets. Their rides and ratings stay for history.
- Admin deactivate → `is_active=false` + ban the user through Clerk's Backend API (`CLERK_SECRET_KEY`), which ends their sessions. Reactivate → unban. If the Clerk call fails, the DB change still applies (it's enforced anyway) and the failure is logged.
- `last_login_at` is updated on an authenticated request when it's older than 1 hour. It feeds `active_users` in analytics.
- `phone` is optional and unverified, but wherever it is written — onboarding and `PATCH /users/me` alike — it must match the shared `Phone` format in `openapi.yaml`: digits, spaces, hyphens, parentheses, dots and an optional leading `+`, 7–20 characters after the `+`. So `+1 (555) 010-9999` and `+1.555.0199` are accepted as typed, while `""`, `abc` and `12345` are 422. One schema, so the two write paths can't drift apart again.
- `preferences` read → the server fills defaults for missing keys (`UserPreferences`). Writes use `UserPreferencesPatch`, which carries no defaults: `PATCH` and onboarding shallow-merge what is sent (the `notifications` sub-object is merged too), an absent key is left alone, and `default_mode: null` clears it. Booleans must be real JSON booleans — `"yes"` is a 422.

## 5. Error codes

| HTTP | code | When |
|---|---|---|
| 400 | `INVALID_WEBHOOK_SIGNATURE` | Clerk webhook with a missing or bad Svix signature |
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
| 422 | `VALIDATION_ERROR` | schema validation; `details` lists fields |
| 422 | `UNDERAGE` / `TERMS_NOT_ACCEPTED` / `DEPARTURE_IN_PAST` | specific validation failures |

## 6. WebSocket protocol

- Connect: `GET /api/v1/ws?token=<clerk_session_token>`, with a fresh token from `getToken()` right before connecting. Browsers can't set headers on a WebSocket, hence the query param. An invalid or expired token, or no profile → the server closes with code **4401**; a deactivated account → **4403**. On 4401, the client gets a new token and reconnects with backoff.
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
| D16 | **Ride preferences on `PATCH` shallow-merge**, absent keys left alone — same rule as user preferences (2026-10-01) | Asked by @frontend: the Edit Ride form has to know whether a partial object wipes the rest. One merge rule for both kinds of preferences is less to remember |
| D17 | **The `Phone` format applies to `PATCH /users/me`, not just onboarding** (2026-10-01). Breaking: a loose phone that used to be accepted is now 422 | @tests and @frontend both flagged the inconsistency. One `Phone` schema is now shared by both request bodies so they can't drift |
| D18 | **`Phone` widened to allow parentheses and dots** (2026-10-01), so `+1 (555) 010-9999` is valid. Additive — nothing that was accepted became invalid | @tests and @frontend independently called parenthesised numbers a natural thing to type. Cheaper to widen before the profile editor is built against the strict rule |
| D20 | **`Ride.my_request` added** (2026-10-01): `{id, status, seats_requested} | null`, the caller's own blocking request on that ride. Additive. §7 is deliberately **unchanged** — a previously-rejected ride stays a search candidate | @frontend was reading `/requests/mine?limit=100` and scanning it to decide what the passenger Ride Details screen should offer, which silently breaks past 100 closed requests. A status alone wouldn't do: cancelling needs the request **id**, so the object carries it. It also lets a search card show a ride the driver already refused as refused, instead of offering a button whose only answer is `PREVIOUSLY_REJECTED` — @backend and @frontend both preferred showing it greyed out with a reason over making it vanish, hence §7 standing pat (Dvir approved both halves) |
| D19 | **The Phase 2 edge cases are now written down** (2026-10-01): the 409 order on creating a request, `available_seats` returning to `capacity` when a ride is cancelled, a locked field counting as a change by presence, `DEPARTURE_IN_PAST` applying to `PATCH` too, `INVALID_STATE_TRANSITION` (not `TOO_LATE_TO_CANCEL`) once the ride has started, `NOT_ENOUGH_SEATS` when approving on a `full` ride, and an unknown `status` filter being a 422. Each one was undefined before, so nothing documented changed meaning | Writing the ride loop turned up seven places where two readings were equally defensible. @tests has to assert exactly one of them, so the contract now says which |

## 9. Scope — what's in v1 and what's later (decided 2026-09-30)

| # | Item | Scope | Notes |
|---|---|---|---|
| G1 | Vehicle info | **v1** | See §4 Vehicles, D14 |
| G2 | Payment methods | later | Hide from the Profile screen. Payment is off-app (cash/Bit); price is informational |
| G3 | Phone verification (SMS) | later | Phone is an unverified profile field |
| G4 | Avg match score in analytics | later | Removed from `AnalyticsSummary`. Would need `match_score` stored on `ride_requests` |
| G5a | Address autocomplete (address → lat/lng) | **v1** | Frontend only, **Mapbox** Search/Geocoding. Sends `*_address` + `*_lat/lng` exactly as the contract says; the backend doesn't call Mapbox |
| G5b | Map / route preview | later | Search results "map toggle" and Create Ride "route preview" are hidden in v1 |
| G6 | Web push notifications | later | WebSocket + email only. `preferences.notifications.push` is stored but unused |
| G7 | Approved passenger cancels | **v1** | Until 1h before departure — see §3, D15 |
| — | Email verification | done | Clerk (required at sign-up) |
