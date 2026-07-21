"""Composição da aplicação FastAPI."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from video_variations.api import storage
from video_variations.api.errors import (
    ProblemError,
    problem_error_handler,
    unhandled_error_handler,
)
from video_variations.api.repository import JobRepository
from video_variations.api.routes import health, jobs
from video_variations.api.runner import JobRunner
from video_variations.core.probe import find_binary
from video_variations.settings import Settings, get_settings

logger = logging.getLogger(__name__)

API_PREFIX = "/api/v1"


async def _cleanup_loop(app: FastAPI, settings: Settings) -> None:
    """Apaga periodicamente os jobs que passaram do período de retenção."""
    repository: JobRepository = app.state.repository
    while True:
        try:
            await asyncio.sleep(settings.cleanup_interval_seconds)
            expired = await repository.list_expired_jobs(settings.retention_hours)
            for job in expired:
                await storage.remove_path(Path(job["output_dir"]))
                await storage.remove_path(Path(job["input_path"]))
                await repository.mark_expired(job["job_id"])
            if expired:
                logger.info("Limpeza removeu %d jobs expirados.", len(expired))

            orfaos = await storage.remove_stale_uploads(
                settings.uploads_dir, settings.retention_hours
            )
            if orfaos:
                logger.info("Limpeza removeu %d upload(s) órfão(s).", orfaos)
        except asyncio.CancelledError:
            raise
        except Exception:  # pragma: no cover - a limpeza não pode derrubar o app
            logger.exception("Falha na rotina de limpeza.")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
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

    app.state.repository = repository
    app.state.runner = JobRunner(repository, settings)
    cleanup_task = asyncio.create_task(_cleanup_loop(app, settings), name="cleanup")

    try:
        yield
    finally:
        cleanup_task.cancel()
        await asyncio.gather(cleanup_task, return_exceptions=True)
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

    app.add_exception_handler(ProblemError, problem_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)

    app.include_router(jobs.router, prefix=API_PREFIX)
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
        "video_variations.api.main:app",
        host="127.0.0.1",
        port=8000,
        workers=1,
    )
