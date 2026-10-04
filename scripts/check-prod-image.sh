#!/usr/bin/env bash
# Production-like check of the backend image, locally.
#
# Builds backend/Dockerfile, then against the compose Postgres and Redis (`docker compose up -d`):
#   1. an incomplete APP_ENV=production config must refuse to start
#   2. the release command (`alembic upgrade head`) migrates a scratch database
#   3. the server starts with a complete production-style config
#   4. /health is 200, /ready is 200 with db=true, /docs is 404, the container turns healthy
# Everything it creates is removed at the end. Run from the repo root:  bash scripts/check-prod-image.sh
set -euo pipefail

IMAGE=ridematch-backend:local
NETWORK=ridematch_default          # compose's network, so the container reaches db:5432 / redis:6379
DB_CONTAINER=ridematch-db-1
SCRATCH_DB=ridematch_prodcheck
CONTAINER=ridematch-prodcheck
HOST_PORT=8099

step() { printf '\n== %s\n' "$*"; }
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }

cleanup() {
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
  docker exec "$DB_CONTAINER" psql -U ridematch -d postgres -qc \
    "DROP DATABASE IF EXISTS $SCRATCH_DB WITH (FORCE)" >/dev/null 2>&1 || true
}
trap cleanup EXIT

step "build $IMAGE"
docker build -q -t "$IMAGE" backend >/dev/null

step "scratch database $SCRATCH_DB"
docker exec "$DB_CONTAINER" psql -U ridematch -d postgres -qc "DROP DATABASE IF EXISTS $SCRATCH_DB WITH (FORCE)"
docker exec "$DB_CONTAINER" psql -U ridematch -d postgres -qc "CREATE DATABASE $SCRATCH_DB"

# A throwaway RSA public key, so CLERK_JWT_KEY parses the way a real Clerk PEM does.
PEM=$(docker run --rm --entrypoint python "$IMAGE" -c "
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
key = rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key()
print(key.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode())")

PROD_ENV=(
  -e APP_ENV=production
  -e "DATABASE_URL=postgresql://ridematch:ridematch@db:5432/$SCRATCH_DB"   # the plain scheme hosts hand out
  -e REDIS_URL=redis://redis:6379/13
  -e CLERK_ISSUER=https://clerk.ridematch.example
  -e "CLERK_JWT_KEY=$PEM"
  -e CLERK_AUTHORIZED_PARTIES=https://app.ridematch.example
  -e CORS_ORIGINS=https://app.ridematch.example
  -e CLERK_SECRET_KEY=sk_live_prodcheck
  -e CLERK_WEBHOOK_SIGNING_SECRET=whsec_cHJvZGNoZWNrLXByb2RjaGVjaw==
  -e EMAIL_BACKEND=smtp
  -e SMTP_HOST=smtp.ridematch.example
  -e EMAIL_FROM=noreply@ridematch.example
  -e ADMIN_EMAIL=
  -e LOG_LEVEL=INFO
)

step "1. an incomplete production config refuses to start"
bad_log=$(mktemp)
if docker run --rm --network "$NETWORK" -e APP_ENV=production "$IMAGE" >"$bad_log" 2>&1; then
  fail "the server started without a production config"
fi
grep -q "Invalid production configuration" "$bad_log" || fail "no validation message"
rm -f "$bad_log"
echo "refused, as it should"

step "2. release command: alembic upgrade head"
docker run --rm --network "$NETWORK" "${PROD_ENV[@]}" "$IMAGE" alembic upgrade head

step "3. start the server"
docker run -d --name "$CONTAINER" --network "$NETWORK" -p "$HOST_PORT:8000" "${PROD_ENV[@]}" "$IMAGE" >/dev/null

base="http://127.0.0.1:$HOST_PORT/api/v1"
for _ in $(seq 1 30); do
  curl -fsS "$base/health" >/dev/null 2>&1 && break
  sleep 1
done

step "4. endpoints"
health=$(curl -fsS "$base/health") || fail "/health unreachable"
[ "$health" = '{"status":"ok"}' ] || fail "/health returned $health"
echo "/health  $health"

ready=$(curl -fsS "$base/ready") || fail "/ready not 200"
echo "$ready" | grep -q '"db":true' || fail "/ready returned $ready"
echo "/ready   $ready"

docs=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$HOST_PORT/docs")
[ "$docs" = 404 ] || fail "/docs returned $docs in production"
echo "/docs    $docs"

for _ in $(seq 1 40); do
  state=$(docker inspect -f '{{.State.Health.Status}}' "$CONTAINER")
  [ "$state" = healthy ] && break
  sleep 2
done
[ "$state" = healthy ] || fail "container health is $state"
echo "HEALTHCHECK $state"

docker logs "$CONTAINER" 2>&1 | grep -q '"app.main"\|config env=production' || fail "no startup config line"
if docker logs "$CONTAINER" 2>&1 | grep -q "sk_live_prodcheck\|whsec_"; then
  fail "a secret appeared in the logs"
fi
echo "logs: JSON, startup config line present, no secrets"

printf '\nOK: the production image builds, migrates, starts and reports ready.\n'
