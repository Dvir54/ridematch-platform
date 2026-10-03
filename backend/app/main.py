"""App factory: routers under `API_PREFIX`, the error envelope, DB/Redis handles on `app.state`.

`create_app(settings)` takes an explicit `Settings` so tests can build an app against the test
database without touching the process environment.
"""

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.auth.clerk import ClerkVerifier
from app.config import Settings, get_settings
from app.db import create_engine, create_sessionmaker
from app.errors import install_error_handlers
from app.health import router as health_router
from app.jobs import jobs_loop
from app.logging_setup import RequestLogMiddleware, configure_logging
from app.modules.admin.router import router as admin_router
from app.modules.feedback.router import router as feedback_router
from app.modules.notifications.router import router as notifications_router
from app.modules.requests.router import router as requests_router
from app.modules.rides.router import router as rides_router
from app.modules.search.router import router as search_router
from app.modules.users.router import router as users_router
from app.modules.webhooks.router import router as webhooks_router
from app.redis_client import create_redis
from app.ws import WsRegistry
from app.ws import router as ws_router

logger = logging.getLogger("app.main")

ROUTERS = (
    health_router,
    users_router,
    rides_router,
    requests_router,
    search_router,
    feedback_router,
    notifications_router,
    admin_router,
    webhooks_router,
    ws_router,
)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, json_logs=settings.app_env == "production")
    logger.info(
        "config env=%s issuer=%s parties=%s db_host=%s",
        settings.app_env,
        settings.clerk_issuer or "-",
        ",".join(settings.clerk_authorized_parties) or "-",
        urlsplit(settings.effective_database_url).hostname or "-",
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        # The background jobs run in this process (CONTRACT.md §7); tests set JOBS_ENABLED=false
        # and call the passes directly with their own `now`.
        jobs_task = asyncio.create_task(jobs_loop(app)) if settings.jobs_enabled else None
        try:
            yield
        finally:
            if jobs_task is not None:
                jobs_task.cancel()
                with suppress(asyncio.CancelledError):
                    await jobs_task
            await app.state.engine.dispose()
            await app.state.redis.aclose()

    app = FastAPI(
        title="RideMatch API",
        version=__version__,
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/docs",
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
    app.state.ws_registry = WsRegistry(app.state.redis)
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

    app.add_middleware(RequestLogMiddleware)
    install_error_handlers(app)
    for router in ROUTERS:
        app.include_router(router, prefix=settings.api_prefix)
    return app


app = create_app()
