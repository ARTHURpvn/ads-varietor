"""Contratos de request e response da API."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ads_varietor.api.repository import JobStatus
from ads_varietor.core.models import ProcessingMode


class VariationParamsView(BaseModel):
    """Subconjunto dos parâmetros exibido ao cliente."""

    speed: float
    filter_type: str
    filter_value: float
    background_color: str
    # Sempre >= 1: é quanto o vídeo foi ampliado antes de o excedente ser
    # cortado nas bordas.
    video_scale: float
    # Com default porque jobs gravados antes da troca de `bg_opacity` e
    # `video_opacity` por `tint_opacity` não têm este campo no JSON salvo.
    # Sem o default, consultar um job antigo devolvia 500.
    tint_opacity: float = 0.0
    noise_audio: bool


class VariationView(BaseModel):
    variation_id: str
    status: str
    error: str | None = None
    size_bytes: int | None = None
    md5: str | None = None
    params: VariationParamsView


class JobProgress(BaseModel):
    total: int
    completed: int
    failed: int


class JobCreatedResponse(BaseModel):
    job_id: str
    status: JobStatus
    num_variations: int
    mode: ProcessingMode
    created_at: str


class JobDetailResponse(BaseModel):
    job_id: str
    status: JobStatus
    num_variations: int
    mode: ProcessingMode
    source_md5: str | None = None
    created_at: str
    updated_at: str
    error: str | None = None
    progress: JobProgress
    variations: list[VariationView] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    ffmpeg_version: str


class KeyUsage(BaseModel):
    """Consumo da chave que fez a pergunta. Nunca o de outra chave."""

    jobs: int
    jobs_by_status: dict[str, int] = Field(default_factory=dict)
    used_bytes: int
    quota_bytes: int
    available_bytes: int
    usage_percent: float


class UsageResponse(BaseModel):
    """Foto do consumo de disco do serviço no momento da consulta."""

    used_bytes: int
    quota_bytes: int
    available_bytes: int
    usage_percent: float
    warn_percent: int
    over_threshold: bool
    retention_hours: int
    jobs_by_status: dict[str, int] = Field(default_factory=dict)
    your_usage: KeyUsage
