"""Configuração da aplicação, lida de variáveis de ambiente."""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuração global. Todos os campos vêm de env ou do arquivo .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Armazenamento ---------------------------------------------------
    storage_dir: Path = Field(
        default=Path("storage"),
        description="Raiz onde ficam uploads, saídas dos jobs e o banco.",
    )
    max_upload_bytes: int = Field(
        default=200 * 1024 * 1024,
        gt=0,
        description="Tamanho máximo aceito por upload.",
    )
    max_storage_bytes: int = Field(
        default=20 * 1024 * 1024 * 1024,
        gt=0,
        description="Quota total de disco para o serviço.",
    )
    retention_hours: int = Field(
        default=24,
        gt=0,
        description="Horas até um job concluído ser apagado.",
    )
    cleanup_interval_seconds: int = Field(
        default=900,
        gt=0,
        description="Intervalo entre execuções da rotina de limpeza.",
    )

    # --- Processamento ---------------------------------------------------
    max_variations_per_job: int = Field(default=50, gt=0, le=500)
    max_concurrent_ffmpeg: int = Field(default=4, gt=0, le=64)
    ffmpeg_timeout_seconds: int = Field(default=300, gt=0)

    # --- Segurança -------------------------------------------------------
    api_keys: str = Field(
        default="",
        description="Chaves de API válidas, separadas por vírgula.",
    )
    rate_limit_jobs_per_hour: int = Field(default=20, gt=0)
    rate_limit_requests_per_minute: int = Field(default=120, gt=0)
    cors_origins: str = Field(
        default="",
        description="Origens permitidas no CORS, separadas por vírgula.",
    )

    @field_validator("storage_dir")
    @classmethod
    def _resolve_storage_dir(cls, value: Path) -> Path:
        return value.expanduser().resolve()

    @property
    def uploads_dir(self) -> Path:
        return self.storage_dir / "uploads"

    @property
    def jobs_dir(self) -> Path:
        return self.storage_dir / "jobs"

    @property
    def database_path(self) -> Path:
        return self.storage_dir / "jobs.sqlite3"

    @property
    def api_key_hashes(self) -> frozenset[str]:
        """Hashes SHA-256 das chaves configuradas.

        A chave em texto puro nunca é mantida em memória depois da carga.
        """
        keys = (key.strip() for key in self.api_keys.split(","))
        return frozenset(
            hashlib.sha256(key.encode("utf-8")).hexdigest() for key in keys if key
        )

    @property
    def cors_origin_list(self) -> list[str]:
        origins = (origin.strip() for origin in self.cors_origins.split(","))
        return [origin for origin in origins if origin]

    def ensure_directories(self) -> None:
        """Cria os diretórios de armazenamento se ainda não existirem."""
        for directory in (self.storage_dir, self.uploads_dir, self.jobs_dir):
            directory.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Instância única de configuração, reutilizada em todo o processo."""
    return Settings()
