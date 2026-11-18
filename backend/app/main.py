"""FastAPI application entrypoint and lifecycle wiring."""

from __future__ import annotations

import logging
import threading
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes.health import root_health_router
from app.api.v1.router import api_v1_router
from app.core.cache import CacheService, RedisConnectionManager
from app.core.config import Settings, get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestCorrelationMiddleware
from app.core.rate_limit import InMemorySlidingWindowRateLimiter
from app.db.session import create_db_engine, create_session_factory, verify_database_connection

logger = logging.getLogger(__name__)

_worker_wake_event = threading.Event()
_worker_stop_event = threading.Event()
_worker_thread: threading.Thread | None = None
_worker_threads: list[threading.Thread] = []
_worker_engine: Any | None = None


def signal_worker_activity() -> None:
    """Notify in-process background worker lanes that new jobs are queued."""
    _worker_wake_event.set()


def _build_lifespan(
    settings: Settings,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(settings.log_level)
        engine = create_db_engine(settings)
        session_factory = create_session_factory(engine)
        http_client = httpx.AsyncClient()
        sync_http_client = httpx.Client(follow_redirects=False)
        redis_mgr = RedisConnectionManager(settings)
        redis_mgr.initialize()
        cache_service = CacheService(settings, redis_mgr=redis_mgr)

        app.state.settings = settings
        app.state.db_engine = engine
        app.state.session_factory = session_factory
        app.state.http_client = http_client
        app.state.sync_http_client = sync_http_client
        app.state.redis_manager = redis_mgr
        app.state.cache_service = cache_service
        if getattr(app.state, "auth_rate_limiter", None) is None:
            app.state.auth_rate_limiter = InMemorySlidingWindowRateLimiter()

        try:
            latency_ms = verify_database_connection(engine)
            logger.info("PostgreSQL startup check succeeded (%.2f ms)", latency_ms)
            # Pre-warm extra pool connections so concurrent queries don't incur 4-5s SSL handshakes
            warm_conns = []
            try:
                for _ in range(3):
                    warm_conns.append(engine.connect())
            finally:
                for conn in warm_conns:
                    conn.close()
            logger.info("PostgreSQL connection pool pre-warmed (4 total connections ready)")
        except Exception as exc:
            # Allow process boot cleanly in dev/health checks while /health/ready reports 503.
            logger.warning(
                "PostgreSQL unavailable during startup check (%s)",
                type(exc).__name__,
            )

        # Launch three independent background worker lanes in daemon threads
        # (Lane A: Source Sync, Lane B: Document/Indexing Preparation, Lane C: Semantic Enrichment)
        global _worker_thread, _worker_threads, _worker_engine
        if settings.app_env != "test":
            try:
                from app.repositories.job import BackgroundJobRepository
                with session_factory() as startup_session:
                    try:
                        recovered = BackgroundJobRepository(startup_session).recover_orphaned_jobs()
                        startup_session.commit()
                        if recovered > 0:
                            logger.info("Recovered %d orphaned running jobs on startup.", recovered)
                    except Exception as rec_exc:
                        logger.warning("Could not recover orphaned jobs on startup: %s", rec_exc)

                from app.worker import build_worker_service

                composite_worker, _worker_engine = build_worker_service(settings)
                poll_interval = max(1.0, float(settings.ingestion.worker_poll_interval_seconds))
                lane_events: dict[str, threading.Event] = {
                    "IPKRHLaneA-Sync": threading.Event(),
                    "IPKRHLaneB-Prep": threading.Event(),
                    "IPKRHLaneC-Semantic": threading.Event(),
                }

                def _make_lane_runner(lane_name: str, step_fn: Callable[[], bool]) -> Callable[[], None]:
                    lane_ev = lane_events[lane_name]

                    def _lane_runner() -> None:
                        logger.info(
                            "In-process background worker lane '%s' active (worker_id=%s)",
                            lane_name,
                            composite_worker.worker_id,
                        )
                        while not _worker_stop_event.is_set():
                            try:
                                did_work = step_fn()
                                if did_work:
                                    for ev in lane_events.values():
                                        ev.set()
                                    continue
                            except Exception as loop_exc:
                                logger.warning(
                                    "Background worker lane '%s' transient loop error: %s",
                                    lane_name,
                                    loop_exc,
                                )
                            # Wait on either global wake or lane wake
                            if _worker_wake_event.is_set():
                                _worker_wake_event.clear()
                                for ev in lane_events.values():
                                    ev.set()
                            lane_ev.wait(timeout=poll_interval)
                            lane_ev.clear()
                        logger.info("In-process background worker lane '%s' stopped.", lane_name)

                    return _lane_runner

                lane_specs = [
                    ("IPKRHLaneA-Sync", composite_worker.process_sync_lane_job),
                    ("IPKRHLaneB-Prep", composite_worker.process_preparation_lane_job),
                    ("IPKRHLaneC-Semantic", composite_worker.process_semantic_lane_job),
                ]
                _worker_threads = []
                for lane_name, step_fn in lane_specs:
                    t = threading.Thread(
                        target=_make_lane_runner(lane_name, step_fn),
                        name=lane_name,
                        daemon=True,
                    )
                    t.start()
                    _worker_threads.append(t)

                _worker_thread = _worker_threads[0]
                app.state.worker_thread = _worker_thread
                app.state.worker_threads = _worker_threads
                logger.info("IPKRH 3-lane background worker threads launched successfully.")
            except Exception as worker_init_exc:
                logger.warning(
                    "Could not initialize in-process background worker thread: %s",
                    worker_init_exc,
                )

        try:
            yield
        finally:
            _worker_stop_event.set()
            _worker_wake_event.set()
            for t in _worker_threads:
                if t.is_alive():
                    t.join(timeout=2.0)
            if _worker_thread is not None and _worker_thread.is_alive():
                _worker_thread.join(timeout=2.0)
            if _worker_engine is not None:
                try:
                    _worker_engine.dispose()
                except Exception:
                    pass
            sync_http_client.close()
            await http_client.aclose()
            redis_mgr.close()
            engine.dispose()
            logger.info("Backend application resources disposed cleanly")

    return lifespan


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application instance."""
    active_settings = settings or get_settings()
    configure_logging(active_settings.log_level)

    docs_url = None if active_settings.is_production else "/docs"
    redoc_url = None if active_settings.is_production else "/redoc"
    openapi_url = None if active_settings.is_production else "/openapi.json"

    application = FastAPI(
        title=active_settings.app_name,
        version=__version__,
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
        lifespan=_build_lifespan(active_settings),
    )

    # Set attributes upfront so routes inspectable before/without lifespan triggers still see them,
    # while lifespan manages connection pool & client lifecycle cleanly.
    application.state.settings = active_settings
    application.state.auth_rate_limiter = InMemorySlidingWindowRateLimiter()

    register_exception_handlers(application)

    cors_regex = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$" if not active_settings.is_production else None

    application.add_middleware(
        CORSMiddleware,
        allow_origins=active_settings.cors_allowed_origins,
        allow_origin_regex=cors_regex,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    application.add_middleware(RequestCorrelationMiddleware)

    application.include_router(root_health_router)
    application.include_router(api_v1_router, prefix="/api/v1")

    return application


app = create_app()
