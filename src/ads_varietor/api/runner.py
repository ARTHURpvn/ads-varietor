"""Execução dos jobs de variação em segundo plano.

Cada job vira uma asyncio.Task registrada aqui, o que permite cancelá-la —
e, por consequência, matar os processos de FFmpeg em andamento.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from ads_varietor.api.observability import log_event
from ads_varietor.core.batch import render_batch
from ads_varietor.core.models import (
    ProcessingMode,
    VariationParams,
    VariationResult,
    VariationStatus,
)
from ads_varietor.core.probe import probe_video
from ads_varietor.api.repository import JobRepository, JobStatus
from ads_varietor.settings import Settings

logger = logging.getLogger(__name__)

# Avanço mínimo, em fração, para gravar o progresso de uma variação. Com 5%
# são cerca de 20 escritas por variação, o suficiente para a barra andar de
# forma contínua sem transformar cada job num carrossel de UPDATEs.
PASSO_DO_PROGRESSO = 0.05


class JobRunner:
    """Registra e controla as tasks de processamento em andamento."""

    def __init__(self, repository: JobRepository, settings: Settings) -> None:
        self._repository = repository
        self._settings = settings
        self._tasks: dict[str, asyncio.Task[None]] = {}
        # Um único semáforo para o serviço inteiro: se cada job tivesse o
        # seu, dez jobs simultâneos abririam dez vezes o limite de processos
        # de FFmpeg e saturariam a máquina.
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_ffmpeg)

    def start(
        self, *, job_id: str, input_path: Path, output_dir: Path,
        variations: list[VariationParams],
        mode: ProcessingMode = ProcessingMode.FULL,
        owner: str | None = None,
    ) -> None:
        """Dispara o processamento do job sem esperar pela conclusão."""
        task = asyncio.create_task(
            self._run(
                job_id=job_id,
                input_path=input_path,
                output_dir=output_dir,
                variations=variations,
                mode=mode,
                owner=owner,
            ),
            name=f"job-{job_id}",
        )
        self._tasks[job_id] = task
        task.add_done_callback(lambda _: self._tasks.pop(job_id, None))

    async def cancel(self, job_id: str) -> bool:
        """Cancela o job e aguarda o encerramento dos processos filhos."""
        task = self._tasks.get(job_id)
        if task is None or task.done():
            return False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return True

    async def shutdown(self) -> None:
        """Cancela tudo que estiver em andamento no desligamento."""
        for job_id in list(self._tasks):
            await self.cancel(job_id)

    async def _run(
        self,
        *,
        job_id: str,
        input_path: Path,
        output_dir: Path,
        variations: list[VariationParams],
        mode: ProcessingMode = ProcessingMode.FULL,
        owner: str | None = None,
    ) -> None:
        await self._repository.set_job_status(job_id, JobStatus.RUNNING)
        inicio = time.monotonic()

        async def on_result(result: VariationResult) -> None:
            await self._repository.set_variation_result(
                job_id=job_id,
                variation_id=result.variation_id,
                status=result.status.value,
                error=result.error,
                size_bytes=result.size_bytes,
                md5=result.md5,
            )

        # O FFmpeg publica progresso várias vezes por segundo. Gravar tudo
        # encheria o banco de escritas sem que a tela ganhasse nada: o
        # frontend consulta a cada 1 a 5 segundos. Só um avanço de PASSO_DO
        # _PROGRESSO vira UPDATE.
        ultimo_gravado: dict[str, float] = {}

        async def on_progress(variation_id: str, fracao: float) -> None:
            anterior = ultimo_gravado.get(variation_id, 0.0)
            if fracao < 1.0 and fracao - anterior < PASSO_DO_PROGRESSO:
                return
            ultimo_gravado[variation_id] = fracao
            await self._repository.set_variation_progress(
                job_id=job_id, variation_id=variation_id, progress=fracao
            )

        try:
            try:
                info = await probe_video(input_path)
                results = await render_batch(
                    input_video=input_path,
                    output_dir=output_dir,
                    variations=variations,
                    timeout_seconds=self._settings.ffmpeg_timeout_seconds,
                    on_result=on_result,
                    info=info,
                    semaphore=self._semaphore,
                    mode=mode,
                    preset=self._settings.ffmpeg_preset,
                    threads=self._settings.ffmpeg_threads,
                    on_progress=on_progress,
                )
            except asyncio.CancelledError:
                # As variações que não chegaram a rodar ficariam eternamente
                # "na fila" na tela do usuário se não fossem encerradas aqui.
                await self._repository.fail_unfinished_variations(
                    job_id, "Cancelado antes de terminar."
                )
                await self._repository.set_job_status(job_id, JobStatus.CANCELLED)
                self._log_terminal(
                    "job.cancelled", job_id, owner, inicio, bytes_total=None
                )
                raise
            except Exception:
                logger.exception("Falha ao processar o job %s", job_id)
                await self._repository.set_job_status(
                    job_id,
                    JobStatus.FAILED,
                    "Não foi possível processar o vídeo enviado.",
                )
                self._log_terminal(
                    "job.failed", job_id, owner, inicio, bytes_total=None
                )
                return

            gerados = sum(
                result.size_bytes or 0
                for result in results
                if result.status is VariationStatus.COMPLETED
            )
            succeeded = any(
                result.status is VariationStatus.COMPLETED for result in results
            )
            if succeeded:
                await self._repository.set_job_status(job_id, JobStatus.COMPLETED)
                self._log_terminal(
                    "job.completed", job_id, owner, inicio, bytes_total=gerados
                )
            else:
                await self._repository.set_job_status(
                    job_id,
                    JobStatus.FAILED,
                    "Nenhuma variação pôde ser gerada a partir deste vídeo.",
                )
                self._log_terminal(
                    "job.failed", job_id, owner, inicio, bytes_total=0
                )
        finally:
            # O vídeo de entrada some em qualquer desfecho — sucesso, falha
            # ou cancelamento. Apagar só no caminho feliz deixava o arquivo
            # original no disco por todo o período de retenção justamente
            # nos casos em que ele não serve mais para nada.
            await self._discard_input(input_path, job_id)

    async def _discard_input(self, input_path: Path, job_id: str) -> None:
        """Apaga o upload sem deixar a falha de I/O escapar.

        Este método roda no `finally` de um caminho que pode estar tratando
        um cancelamento: uma exceção aqui mascararia o motivo real.
        """
        try:
            await asyncio.shield(asyncio.to_thread(input_path.unlink, True))
        except OSError:
            logger.warning(
                "Não foi possível apagar a entrada do job %s.", job_id
            )

    @staticmethod
    def _log_terminal(
        event: str,
        job_id: str,
        owner: str | None,
        inicio: float,
        *,
        bytes_total: int | None,
    ) -> None:
        log_event(
            logger,
            event,
            job_id=job_id,
            owner=owner,
            duration_seconds=time.monotonic() - inicio,
            bytes_total=bytes_total,
        )
