"""Contratos de request e response da API."""

from __future__ import annotations

from pydantic import BaseModel, Field

from video_variations.api.repository import JobStatus


class VariationParamsView(BaseModel):
    """Subconjunto dos parâmetros exibido ao cliente."""

    speed: float
    filter_type: str
    filter_value: float
    background_color: str
    video_scale: float
    noise_audio: bool


class VariationView(BaseModel):
    variation_id: str
    status: str
    error: str | None = None
    size_bytes: int | None = None
    params: VariationParamsView


class JobProgress(BaseModel):
    total: int
    completed: int
    failed: int


class JobCreatedResponse(BaseModel):
    job_id: str
    status: JobStatus
    num_variations: int
    created_at: str


class JobDetailResponse(BaseModel):
    job_id: str
    status: JobStatus
    num_variations: int
    created_at: str
    updated_at: str
    error: str | None = None
    progress: JobProgress
    variations: list[VariationView] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    ffmpeg_version: str
