"""Rota de visibilidade de consumo de disco.

Autenticada de propósito: os números globais dizem quanto falta para o
serviço parar de aceitar jobs, o que é informação operacional.
"""

from __future__ import annotations

from fastapi import APIRouter, Response

from video_variations.api import storage
from video_variations.api.deps import AppSettings, RateLimitedKey, Repository
from video_variations.api.schemas import KeyUsage, UsageResponse

router = APIRouter(tags=["usage"])


def _percent(used: int, quota: int) -> float:
    return round(100.0 * used / quota, 2) if quota > 0 else 0.0


@router.get(
    "/usage",
    response_model=UsageResponse,
    summary="Consumo de disco do serviço e da chave que perguntou",
)
async def get_usage(
    api_key_hash: RateLimitedKey,
    repository: Repository,
    settings: AppSettings,
    response: Response,
) -> UsageResponse:
    # O total global vem do disco de verdade: é ele que enche. O total por
    # chave vem do banco, porque o filesystem não sabe de quem é cada byte.
    usados = await storage.get_used_bytes(settings.storage_dir)
    percentual = _percent(usados, settings.max_storage_bytes)

    da_chave = await repository.bytes_used_by_key(api_key_hash)
    jobs_da_chave = await repository.count_jobs_by_status(api_key_hash)

    response.headers["Cache-Control"] = "no-store"
    return UsageResponse(
        used_bytes=usados,
        quota_bytes=settings.max_storage_bytes,
        available_bytes=max(0, settings.max_storage_bytes - usados),
        usage_percent=percentual,
        warn_percent=settings.storage_warn_percent,
        over_threshold=percentual >= settings.storage_warn_percent,
        retention_hours=settings.retention_hours,
        jobs_by_status=await repository.count_jobs_by_status(),
        your_usage=KeyUsage(
            jobs=sum(jobs_da_chave.values()),
            jobs_by_status=jobs_da_chave,
            used_bytes=da_chave,
            quota_bytes=settings.max_storage_bytes_per_key,
            available_bytes=max(
                0, settings.max_storage_bytes_per_key - da_chave
            ),
            usage_percent=_percent(
                da_chave, settings.max_storage_bytes_per_key
            ),
        ),
    )
