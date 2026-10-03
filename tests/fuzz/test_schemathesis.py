"""Schemathesis against contracts/openapi.yaml, over real HTTP.

A uvicorn subprocess serves the backend with the suite's test environment (test
DB, our own Clerk key). Every operation is fuzzed twice: as an ordinary user and
as the admin. Run on demand: `uv run pytest fuzz -q`.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import schemathesis
from hypothesis import HealthCheck, settings
from schemathesis.specs.openapi.checks import (
    allow_header_conformance,
    negative_data_rejection,
    positive_data_acceptance,
    unsupported_method,
)

from support import env as test_env
from support.factories import onboarding_payload, unique_suffix
from support.keys import TokenSigner, auth_header

pytestmark = pytest.mark.fuzz

PORT = 8765
ROOT = f"http://127.0.0.1:{PORT}"
BASE_URL = f"{ROOT}{test_env.API_PREFIX}"
BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"

REJECTS_VALID_INPUT = {
    "/webhooks/clerk",
    "/rides",
    "/rides/{ride_id}",
    "/rides/mine",
    "/requests/mine",
}

schema = schemathesis.openapi.from_path(test_env.OPENAPI_PATH)


@pytest.fixture(scope="module")
def server(database, keys) -> Iterator[None]:
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--port",
            str(PORT),
            "--log-level",
            "warning",
        ],
        cwd=BACKEND_DIR,
        env=os.environ.copy(),
    )
    try:
        deadline = time.monotonic() + 60
        while True:
            try:
                if httpx.get(f"{BASE_URL}/health", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            if process.poll() is not None or time.monotonic() > deadline:
                pytest.fail("backend did not come up for fuzzing")
            time.sleep(0.5)
        yield
    finally:
        process.terminate()
        process.wait(timeout=15)


def _onboarded_headers(signer: TokenSigner, email: str) -> dict[str, str]:
    headers = auth_header(signer.sign(sub=f"user_fuzz_{unique_suffix()}", email=email))
    response = httpx.post(
        f"{BASE_URL}/users/me/onboarding", json=onboarding_payload(), headers=headers
    )
    assert response.status_code == 201, response.text
    return headers


@pytest.fixture(scope="module")
def identities(server, signer) -> dict[str, dict[str, str]]:
    # The admin must onboard first: ADMIN_EMAIL only makes an admin while none exists.
    return {
        "admin": _onboarded_headers(signer, test_env.ADMIN_EMAIL),
        "user": _onboarded_headers(signer, f"fuzz{unique_suffix()}@ridematch.test"),
    }


@pytest.mark.parametrize("who", ["user", "admin"])
@schema.parametrize()
@settings(max_examples=25, deadline=None, suppress_health_check=list(HealthCheck))
def test_api_conforms_to_contract(case, who, identities):
    # /health and the Clerk webhook take no token; a stray header is harmless there.
    # Random data can't carry a valid Svix signature, a past departure_time is schema-valid but
    # refused (DEPARTURE_IN_PAST), and the `status` filter is a free string in openapi.yaml that the
    # contract narrows to an enum (422 on an unknown value).
    rejects_valid = case.operation.path in REJECTS_VALID_INPUT
    # Unknown query params are ignored on GETs by design, and OPTIONS/Allow isn't in the contract.
    skip = [unsupported_method, allow_header_conformance]
    if rejects_valid:
        skip.append(positive_data_acceptance)
    if case.method == "GET":
        skip.append(negative_data_rejection)
    case.call_and_validate(base_url=BASE_URL, headers=identities[who], excluded_checks=skip)
