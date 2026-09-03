"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse, PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app import __version__
from app.api import (
    routes_admin,
    routes_eval,
    routes_generate,
    routes_kb,
    routes_metrics,
    routes_review,
    routes_traces,
)
from app.config import settings
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging, get_logger
from app.core.telemetry import init_telemetry
from app.db.cache import close_redis

log = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    problems = settings.validate_for_runtime()
    if problems:
        for p in problems:
            log.error("config.invalid", problem=p)
        if settings.is_prod:
            raise RuntimeError("refusing to start with invalid production config: " + "; ".join(problems))
    init_telemetry(app)
    log.info("startup", version=__version__, env=settings.env, llm_provider=settings.llm.provider)
    yield
    await close_redis()


app = FastAPI(
    title="MA-AHAF",
    version=__version__,
    description=(
        "Multi-Agent Adaptive Hallucination Attenuation Framework — an adaptive "
        "reliability/creativity control layer between an application and its LLMs."
    ),
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["authorization", "content-type", "x-api-key"],
)

install_error_handlers(app)
for module in (routes_generate, routes_kb, routes_traces, routes_metrics, routes_eval,
               routes_review, routes_admin):
    app.include_router(module.router)


@app.get("/health", tags=["ops"])
async def health() -> dict:
    return {"status": "ok", "version": __version__}


@app.get("/ready", tags=["ops"])
async def ready() -> dict:
    from sqlalchemy import text

    from app.db.session import engine

    checks = {"db": False, "redis": False}
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        checks["db"] = True
    except Exception:  # pragma: no cover
        pass
    try:
        from app.db.cache import get_redis

        await get_redis().ping()
        checks["redis"] = True
    except Exception:  # pragma: no cover
        pass
    ok = all(checks.values())
    return {"ready": ok, "checks": checks}


@app.get("/metrics", include_in_schema=False)
async def metrics() -> PlainTextResponse:
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/v1/graph", tags=["ops"])
async def graph_structure() -> dict:
    """Return the orchestration graph as a mermaid definition (proposal §6)."""
    from app.orchestration.graph import get_compiled_graph

    fallback = (
        "graph TD; intent-->risk-->policy-->generate-->decompose-->retrieve-->verify"
        "-->risk_scoring-->creativity-->decide-->finalize"
    )
    try:
        mermaid = get_compiled_graph().get_graph().draw_mermaid()
    except Exception:  # pragma: no cover
        mermaid = fallback
    return {"mermaid": mermaid}
