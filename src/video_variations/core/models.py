"""Modelos de domínio do motor de variações."""

from __future__ import annotations

import enum
import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

HEX_COLOR_PATTERN = re.compile(r"^[0-9a-fA-F]{6}$")
VARIATION_ID_PATTERN = re.compile(r"^[a-z0-9_]{1,64}$")


class FilterType(str, enum.Enum):
    """Efeito de cor aplicado ao vídeo."""

    NONE = "none"
    BRIGHTNESS = "brightness"
    CONTRAST = "contrast"
    SATURATE = "saturate"
    HUE = "hue"


class VariationParams(BaseModel):
    """Parâmetros que definem uma variação de vídeo.

    Os limites de cada campo são os mesmos aceitos pelo FFmpeg depois da
    conversão feita em `core.ffmpeg`; validar aqui evita montar um
    filtergraph inválido.
    """

    model_config = ConfigDict(frozen=True)

    variation_id: Annotated[str, Field(pattern=VARIATION_ID_PATTERN.pattern)]

    metadata_title: str | None = Field(default=None, max_length=200)
    metadata_author: str | None = Field(default=None, max_length=200)

    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    filter_type: FilterType = FilterType.NONE
    filter_value: float = Field(default=1.0, ge=0.0, le=2.0)

    background_color: Annotated[str, Field(pattern=HEX_COLOR_PATTERN.pattern)] = "000000"
    bg_opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    video_opacity: float = Field(default=1.0, ge=0.1, le=1.0)
    video_scale: float = Field(default=1.0, ge=0.1, le=1.0)

    noise_audio: bool = False
    noise_level: float = Field(default=0.0, ge=0.0, le=1.0)

    overlay_enabled: bool = False
    overlay_opacity: float = Field(default=0.0, ge=0.0, le=1.0)
    overlay_scale: float = Field(default=0.3, ge=0.05, le=1.0)


class VariationStatus(str, enum.Enum):
    """Estado de uma variação individual dentro de um job."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class VariationResult(BaseModel):
    """Resultado do processamento de uma variação."""

    variation_id: str
    status: VariationStatus
    output_path: str | None = None
    size_bytes: int | None = None
    error: str | None = None
    duration_seconds: float | None = None


class VideoInfo(BaseModel):
    """Metadados do vídeo de entrada, extraídos com ffprobe."""

    width: int = Field(gt=0)
    height: int = Field(gt=0)
    duration_seconds: float = Field(ge=0)
    has_audio: bool
    video_codec: str
