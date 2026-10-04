"""Locate the backend's ASGI app.

The project plan says `backend/` is an installable uv package named
`ridematch-backend` "exposing `app`", without naming the import path, so this
tries the plausible spellings and lets `RIDEMATCH_APP=module:attr` override.
Once @backend confirms the real path it can be collapsed to one candidate.
"""

from __future__ import annotations

import importlib
import os

CANDIDATES: tuple[str, ...] = (
    "ridematch_backend.main:app",
    "ridematch_backend:app",
    "ridematch_backend.app.main:app",
    "app.main:app",
    "app:app",
    "backend.app.main:app",
)


class BackendNotInstalled(RuntimeError):
    """The backend package is not importable from this environment."""


def _load(spec: str):
    module_name, _, attr = spec.partition(":")
    module = importlib.import_module(module_name)
    return getattr(module, attr or "app")


def load_app():
    override = os.environ.get("RIDEMATCH_APP")
    if override:
        try:
            return _load(override)
        except (ImportError, AttributeError) as exc:
            raise BackendNotInstalled(
                f"RIDEMATCH_APP={override!r} could not be imported: {exc}"
            ) from exc

    tried: list[str] = []
    for spec in CANDIDATES:
        try:
            return _load(spec)
        except (ImportError, AttributeError) as exc:
            tried.append(f"  {spec}: {exc}")

    raise BackendNotInstalled(
        "Could not import the backend ASGI app. Tried:\n"
        + "\n".join(tried)
        + "\n\nInstall it into this environment (uncomment the ridematch-backend "
        "dependency in tests/pyproject.toml once ../backend is an installable "
        "package) or set RIDEMATCH_APP=module:attr."
    )
