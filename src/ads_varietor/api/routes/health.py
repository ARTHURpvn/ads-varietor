"""Rota de verificação de saúde do serviço."""

from __future__ import annotations

from fastapi import APIRouter

from ads_varietor.api.schemas import HealthResponse
from ads_varietor.core.probe import FFmpegNotFoundError, find_binary

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Estado do serviço")
async def health() -> HealthResponse:
    """Informa se o serviço consegue processar vídeos.

    A rota é pública para servir de healthcheck ao proxy, por isso não
    revela a versão exata do FFmpeg — número de versão de software é
    insumo de reconhecimento para quem procura exploits conhecidos.
    """
    try:
        find_binary("ffmpeg")
        find_binary("ffprobe")
    except FFmpegNotFoundError:
        return HealthResponse(status="degraded", ffmpeg_version="indisponível")
    return HealthResponse(status="ok", ffmpeg_version="disponível")
