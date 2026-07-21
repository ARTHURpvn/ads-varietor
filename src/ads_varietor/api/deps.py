"""Dependências de autenticação e limite de uso."""

from __future__ import annotations

import hashlib
import hmac
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import APIKeyHeader

from ads_varietor.api import errors
from ads_varietor.api.repository import JobRepository
from ads_varietor.settings import Settings, get_settings

API_KEY_HEADER_NAME = "X-API-Key"
JOBS_WINDOW_SECONDS = 3600
REQUESTS_WINDOW_SECONDS = 60

api_key_header = APIKeyHeader(name=API_KEY_HEADER_NAME, auto_error=False)


def get_repository(request: Request) -> JobRepository:
    repository = getattr(request.app.state, "repository", None)
    if repository is None:  # pragma: no cover - só ocorre fora do lifespan
        raise RuntimeError("Repositório não inicializado.")
    return repository


def _matches_configured_key(candidate_hash: str, settings: Settings) -> bool:
    """Compara o hash recebido com os configurados em tempo constante.

    `compare_digest` evita que o tempo de resposta revele quantos caracteres
    da chave estavam certos.
    """
    return any(
        hmac.compare_digest(candidate_hash, known_hash)
        for known_hash in settings.api_key_hashes
    )


async def require_api_key(
    api_key: Annotated[str | None, Depends(api_key_header)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> str:
    """Valida a chave e devolve o hash dela, usado como dono dos jobs.

    Com `UI_PUBLIC` ligado, uma requisição sem chave é aceita e atribuída a
    um dono público compartilhado. Uma chave enviada continua sendo validada:
    mandar chave errada é erro, e não vira acesso público por acidente.
    """
    if not api_key:
        if settings.ui_public:
            return settings.public_owner_hash
        raise errors.unauthorized()

    if not settings.api_key_hashes:
        raise errors.unauthorized()

    candidate_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    if not _matches_configured_key(candidate_hash, settings):
        raise errors.unauthorized()
    return candidate_hash


ApiKeyHash = Annotated[str, Depends(require_api_key)]
Repository = Annotated[JobRepository, Depends(get_repository)]
AppSettings = Annotated[Settings, Depends(get_settings)]


async def enforce_request_rate_limit(
    api_key_hash: ApiKeyHash,
    repository: Repository,
    settings: AppSettings,
) -> str:
    """Limite geral de requisições por minuto, por chave."""
    allowed = await repository.count_and_record_event(
        api_key_hash=api_key_hash,
        event_type="request",
        window_seconds=REQUESTS_WINDOW_SECONDS,
        limit=settings.rate_limit_requests_per_minute,
    )
    if not allowed:
        raise errors.rate_limited(REQUESTS_WINDOW_SECONDS)
    return api_key_hash


async def enforce_job_rate_limit(
    api_key_hash: Annotated[str, Depends(enforce_request_rate_limit)],
    repository: Repository,
    settings: AppSettings,
) -> str:
    """Limite específico de criação de jobs por hora, por chave.

    Criar job é caro (N processos de FFmpeg), então tem um limite próprio,
    bem mais restrito que o de requisições.
    """
    allowed = await repository.count_and_record_event(
        api_key_hash=api_key_hash,
        event_type="job",
        window_seconds=JOBS_WINDOW_SECONDS,
        limit=settings.rate_limit_jobs_per_hour,
    )
    if not allowed:
        raise errors.rate_limited(JOBS_WINDOW_SECONDS)
    return api_key_hash


RateLimitedKey = Annotated[str, Depends(enforce_request_rate_limit)]
JobCreationKey = Annotated[str, Depends(enforce_job_rate_limit)]
