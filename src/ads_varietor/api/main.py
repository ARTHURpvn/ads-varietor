"""Composição da aplicação FastAPI."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from ads_varietor.api import maintenance
from ads_varietor.api.errors import (
    ProblemError,
    http_error_handler,
    problem_error_handler,
    unhandled_error_handler,
    validation_error_handler,
)
from ads_varietor.api.observability import configure_logging
from ads_varietor.api.repository import JobRepository
from ads_varietor.api.routes import health, jobs, usage
from ads_varietor.api.runner import JobRunner
from ads_varietor.core.probe import find_binary
from ads_varietor.settings import get_settings

logger = logging.getLogger(__name__)

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(level=settings.log_level, json_output=settings.log_json)
    settings.ensure_directories()

    # Falhar aqui é melhor que aceitar jobs que nunca vão renderizar.
    find_binary("ffmpeg")
    find_binary("ffprobe")

    if not settings.api_key_hashes:
        raise RuntimeError(
            "Nenhuma API key configurada. Defina API_KEYS antes de iniciar. "
            'Gere uma com: python -c "import secrets; '
            'print(secrets.token_urlsafe(32))"'
        )

    if settings.weak_keys():
        raise RuntimeError(
            "API_KEYS contém chave de exemplo ou curta demais. Substitua por "
            'uma chave gerada: python -c "import secrets; '
            'print(secrets.token_urlsafe(32))"'
        )

    repository = JobRepository(settings.database_path)
    await repository.initialize()

    interrupted = await repository.fail_interrupted_jobs()
    if interrupted:
        logger.warning(
            "%d job(s) interrompido(s) por reinício foram marcados como falha.",
            interrupted,
        )

    # Antes de aceitar tráfego: um crash anterior pode ter deixado diretório
    # sem registro e registro sem diretório, e nenhum dos dois volta a ser
    # candidato à retenção por conta própria.
    if settings.reconcile_enabled:
        await maintenance.run_reconcile(repository, settings)
    await maintenance.check_storage_threshold(settings)

    app.state.repository = repository
    app.state.runner = JobRunner(repository, settings)
    maintenance_task = asyncio.create_task(
        maintenance.maintenance_loop(repository, settings), name="maintenance"
    )

    try:
        yield
    finally:
        maintenance_task.cancel()
        await asyncio.gather(maintenance_task, return_exceptions=True)
        await app.state.runner.shutdown()


def create_app() -> FastAPI:
    """Cria a aplicação com middlewares, rotas e handlers de erro."""
    settings = get_settings()

    app = FastAPI(
        title="Video Variations API",
        version="1.0.0",
        description=(
            "Gera múltiplas variações de um vídeo. O processamento é "
            "assíncrono: crie um job e acompanhe o progresso por polling."
        ),
        lifespan=lifespan,
    )

    origins = settings.cors_origin_list
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["X-API-Key", "Content-Type"],
        )

    # Todos os caminhos de erro precisam sair em problem+json: sem os dois
    # handlers do meio, os erros gerados pelo próprio framework escapariam do
    # contrato e exporiam os detalhes internos da validação.
    app.add_exception_handler(ProblemError, problem_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)

    app.include_router(jobs.router, prefix=API_PREFIX)
    app.include_router(usage.router, prefix=API_PREFIX)
    app.include_router(health.router, prefix=API_PREFIX)
    return app


app = create_app()


def run() -> None:  # pragma: no cover - entrada de execução
    """Sobe o servidor escutando apenas em loopback.

    TLS e exposição pública são responsabilidade do reverse proxy, que
    também injeta o header X-API-Key para o frontend.
    """
    import uvicorn

    uvicorn.run(
        "ads_varietor.api.main:app",
        host="127.0.0.1",
        port=8037,
        workers=1,
    )
