"""Configuração da aplicação, lida de variáveis de ambiente."""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Valores que aparecem no .env.example e em documentação; nenhum deles pode
# valer como credencial de um serviço exposto na internet.
PLACEHOLDER_KEYS = frozenset(
    {
        "troque-esta-chave",
        "changeme",
        "chave",
        "secret",
        "api-key",
    }
)
MINIMUM_API_KEY_LENGTH = 24


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
    max_storage_bytes_per_key: int = Field(
        default=10 * 1024 * 1024 * 1024,
        gt=0,
        description=(
            "Quota de disco por chave de API. Impede que uma única chave "
            "consuma a quota global e trave as demais."
        ),
    )
    max_zip_bytes: int = Field(
        default=4 * 1024 * 1024 * 1024,
        gt=0,
        description="Tamanho máximo do ZIP gerado no download em lote.",
    )
    retention_hours: int = Field(
        default=1,
        gt=0,
        description=(
            "Horas até um job terminado ser apagado. O padrão é curto de "
            "propósito: um job de 50 variações ocupa vários GB e o fluxo "
            "real é criar e baixar em minutos. A hora de folga existe para "
            "cobrir um download que falhou, sem obrigar a refazer o job."
        ),
    )
    cleanup_interval_seconds: int = Field(
        default=900,
        gt=0,
        description="Intervalo entre execuções da rotina de limpeza.",
    )
    delete_after_batch_download: bool = Field(
        default=False,
        description=(
            "Apaga os arquivos do job assim que o download em lote termina. "
            "Libera disco na hora, mas impede rebaixar o mesmo job."
        ),
    )
    reconcile_enabled: bool = Field(
        default=True,
        description=(
            "Reconcilia disco e banco no start e a cada ciclo de limpeza."
        ),
    )
    unreferenced_upload_grace_seconds: int = Field(
        default=3600,
        gt=0,
        description=(
            "Idade mínima de um upload sem job associado para ser apagado "
            "pela reconciliação. A folga evita corrida com um upload que "
            "acabou de ser gravado e ainda não virou registro no banco."
        ),
    )

    # --- Observabilidade -------------------------------------------------
    storage_warn_percent: int = Field(
        default=80,
        ge=1,
        le=100,
        description="Percentual da quota global que dispara aviso no log.",
    )
    log_json: bool = Field(
        default=True,
        description="Emite os logs em JSON de uma linha por evento.",
    )
    log_level: str = Field(
        default="INFO",
        description="Nível mínimo de log (DEBUG, INFO, WARNING, ERROR).",
    )

    # --- Processamento ---------------------------------------------------
    max_variations_per_job: int = Field(default=50, gt=0, le=500)
    max_concurrent_ffmpeg: int = Field(
        default=4,
        gt=0,
        le=64,
        description="Teto global de processos FFmpeg simultâneos no serviço.",
    )
    ffmpeg_timeout_seconds: int = Field(default=300, gt=0)
    ffmpeg_preset: str = Field(
        default="veryfast",
        description=(
            "Preset do libx264. `ultrafast` encoda um pouco mais rápido mas "
            "gera arquivo 2 a 3 vezes maior, o que se paga de volta em disco, "
            "ZIP e download. `veryfast` costuma ser o melhor equilíbrio."
        ),
    )
    ffmpeg_threads: int = Field(
        default=0,
        ge=0,
        description=(
            "Threads por processo de FFmpeg. 0 deixa o FFmpeg decidir, o que "
            "com vários processos simultâneos gera mais threads que núcleos "
            "e desperdiça tempo em troca de contexto. Um valor perto de "
            "(núcleos ÷ MAX_CONCURRENT_FFMPEG) costuma render mais."
        ),
    )
    max_input_pixels: int = Field(
        default=8192 * 8192,
        gt=0,
        description=(
            "Área máxima do vídeo de entrada. O filtergraph aloca um canvas "
            "do tamanho do vídeo, então uma resolução absurda esgota a memória."
        ),
    )
    max_input_duration_seconds: float = Field(
        default=3600.0,
        gt=0,
        description="Duração máxima aceita para o vídeo de entrada.",
    )

    # --- Interface -------------------------------------------------------
    frontend_dir: Path | None = Field(
        default=None,
        description=(
            "Diretório com o build do frontend. Quando existe, a aplicação "
            "serve a interface na mesma origem da API."
        ),
    )
    ui_public: bool = Field(
        default=False,
        description=(
            "Aceita chamadas da interface sem API key. Quem abrir o site "
            "consegue usar a API — que é exatamente o que acontecia quando "
            "um proxy injetava a chave para todo visitante, só que agora "
            "declarado. Deixe desligado se o serviço não deve ser aberto."
        ),
    )

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
    def public_owner_hash(self) -> str:
        """Dono atribuído às requisições da interface sem chave.

        Todas compartilham o mesmo dono, e portanto a mesma quota e o mesmo
        rate limit — a mesma propriedade que o modelo com proxy injetando
        uma chave única já tinha.
        """
        return hashlib.sha256(b"ads-varietor:public-ui").hexdigest()

    @property
    def configured_keys(self) -> list[str]:
        """Chaves declaradas em API_KEYS, sem espaços e sem vazias."""
        return [key.strip() for key in self.api_keys.split(",") if key.strip()]

    @property
    def api_key_hashes(self) -> frozenset[str]:
        """Hashes SHA-256 das chaves configuradas.

        A chave em texto puro nunca é mantida em memória depois da carga.
        """
        return frozenset(
            hashlib.sha256(key.encode("utf-8")).hexdigest()
            for key in self.configured_keys
        )

    def weak_keys(self) -> list[str]:
        """Chaves inaceitáveis: as de exemplo e as curtas demais.

        A chave do .env.example está publicada no repositório; aceitá-la
        equivaleria a subir o serviço sem autenticação nenhuma.
        """
        return [
            key
            for key in self.configured_keys
            if key in PLACEHOLDER_KEYS or len(key) < MINIMUM_API_KEY_LENGTH
        ]

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
