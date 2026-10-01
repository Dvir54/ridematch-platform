"""App factory: routers under `API_PREFIX`, the error envelope, DB/Redis handles on `app.state`.

`create_app(settings)` takes an explicit `Settings` so tests can build an app against the test
database without touching the process environment.
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.auth.clerk import ClerkVerifier
from app.config import Settings, get_settings
from app.db import create_engine, create_sessionmaker
from app.errors import install_error_handlers
from app.health import router as health_router
from app.modules.requests.router import router as requests_router
from app.modules.rides.router import router as rides_router
from app.modules.users.router import router as users_router
from app.redis_client import create_redis

ROUTERS = (health_router, users_router, rides_router, requests_router)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        yield
        await app.state.engine.dispose()
        await app.state.redis.aclose()

    app = FastAPI(
        title="RideMatch API",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
        openapi_url=f"{settings.api_prefix}/openapi.json",
    )

    # Built eagerly (both are lazy about connecting) so an app used without its lifespan — as
    # in-process tests do — still has working handles.
    engine = create_engine(settings)
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessionmaker = create_sessionmaker(engine)
    app.state.redis = create_redis(settings)
    app.state.clerk_verifier = ClerkVerifier(settings)

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["X-Total-Count"],
        )

    install_error_handlers(app)
    for router in ROUTERS:
        app.include_router(router, prefix=settings.api_prefix)
    return app


app = create_app()
