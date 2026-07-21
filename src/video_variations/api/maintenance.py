"""Rotinas de manutenção do armazenamento.

Três responsabilidades separadas, todas idempotentes e seguras para rodar
em paralelo com o serviço atendendo requisições:

- retenção: apaga por idade os jobs já terminados;
- reconciliação: alinha o que existe em disco com o que existe no banco;
- aviso de uso: registra no log quando a quota global fica apertada.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from video_variations.api import storage
from video_variations.api.observability import log_event
from video_variations.api.repository import JobRepository
from video_variations.settings import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReconcileReport:
    """O que a reconciliação encontrou e corrigiu num ciclo."""

    orphan_directories: int = 0
    missing_directories: int = 0
    orphan_uploads: int = 0

    @property
    def is_empty(self) -> bool:
        return not (
            self.orphan_directories
            or self.missing_directories
            or self.orphan_uploads
        )


async def purge_job_files(job: dict[str, object]) -> None:
    """Remove entrada e saída de um job. Tolera arquivo já ausente."""
    output_dir = job.get("output_dir")
    input_path = job.get("input_path")
    if output_dir:
        await storage.remove_path(Path(str(output_dir)))
    if input_path:
        await storage.remove_path(Path(str(input_path)))


async def run_retention(
    repository: JobRepository, settings: Settings
) -> int:
    """Apaga os jobs terminados que passaram do período de retenção."""
    inicio = time.monotonic()
    expirados = await repository.list_expired_jobs(settings.retention_hours)
    for job in expirados:
        await purge_job_files(job)
        await repository.mark_expired(str(job["job_id"]))

    if expirados:
        log_event(
            logger,
            "cleanup.retention",
            duration_seconds=time.monotonic() - inicio,
            jobs_removed=len(expirados),
            retention_hours=settings.retention_hours,
        )
    return len(expirados)


async def run_reconcile(
    repository: JobRepository, settings: Settings
) -> ReconcileReport:
    """Alinha disco e banco depois de uma interrupção no meio de um ciclo.

    Sem isto, um crash entre "apagar arquivos" e "marcar como expirado"
    deixa lixo que nenhuma rotina volta a olhar — o diretório não é mais
    candidato à retenção, e o registro aponta para arquivos inexistentes.
    """
    inicio = time.monotonic()

    # O disco é listado ANTES de consultar o banco. Na ordem inversa, um job
    # criado entre as duas leituras teria seu diretório visto sem estar na
    # lista de esperados — e seria apagado com o trabalho em andamento
    # dentro. Lendo o disco primeiro, um job novo simplesmente não aparece
    # na lista e sobra para o ciclo seguinte.
    diretorios = await storage.list_job_directories(settings.jobs_dir)
    esperados = await repository.job_ids_with_expected_directory()
    orfaos = 0
    for diretorio in diretorios:
        if diretorio.name not in esperados:
            await storage.remove_path(diretorio)
            orfaos += 1

    ausentes = 0
    for job in await repository.list_completed_jobs():
        if not Path(job["output_dir"]).is_dir():
            await repository.mark_expired(job["job_id"])
            ausentes += 1

    ativos = frozenset(await repository.active_input_paths())
    uploads_orfaos = await storage.remove_unreferenced_uploads(
        settings.uploads_dir,
        ativos,
        min_age_seconds=settings.unreferenced_upload_grace_seconds,
    )

    report = ReconcileReport(
        orphan_directories=orfaos,
        missing_directories=ausentes,
        orphan_uploads=uploads_orfaos,
    )
    if not report.is_empty:
        log_event(
            logger,
            "cleanup.reconcile",
            duration_seconds=time.monotonic() - inicio,
            orphan_directories=report.orphan_directories,
            missing_directories=report.missing_directories,
            orphan_uploads=report.orphan_uploads,
        )
    return report


async def check_storage_threshold(settings: Settings) -> float:
    """Loga um aviso quando o uso passa do limiar configurado.

    Devolve o percentual apurado para quem quiser reaproveitar a medição.
    """
    usados = await storage.get_used_bytes(settings.storage_dir)
    percentual = 100.0 * usados / settings.max_storage_bytes

    if percentual >= settings.storage_warn_percent:
        log_event(
            logger,
            "storage.threshold_exceeded",
            level=logging.WARNING,
            bytes_total=usados,
            quota_bytes=settings.max_storage_bytes,
            usage_percent=round(percentual, 2),
            threshold_percent=settings.storage_warn_percent,
        )
    return percentual


async def maintenance_loop(
    repository: JobRepository, settings: Settings
) -> None:
    """Executa retenção, reconciliação e aviso de uso em ciclo."""
    while True:
        try:
            await asyncio.sleep(settings.cleanup_interval_seconds)
            await run_retention(repository, settings)
            if settings.reconcile_enabled:
                await run_reconcile(repository, settings)
            await check_storage_threshold(settings)
        except asyncio.CancelledError:
            raise
        except Exception:  # a manutenção não pode derrubar o serviço
            logger.exception("Falha na rotina de manutenção.")
