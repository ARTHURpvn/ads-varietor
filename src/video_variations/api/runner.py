"""Execução dos jobs de variação em segundo plano.

Cada job vira uma asyncio.Task registrada aqui, o que permite cancelá-la —
e, por consequência, matar os processos de FFmpeg em andamento.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from video_variations.core.batch import render_batch
from video_variations.core.models import (
    VariationParams,
    VariationResult,
    VariationStatus,
)
from video_variations.core.probe import probe_video
from video_variations.api.repository import JobRepository, JobStatus
from video_variations.settings import Settings

logger = logging.getLogger(__name__)


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
    ) -> None:
        """Dispara o processamento do job sem esperar pela conclusão."""
        task = asyncio.create_task(
            self._run(
                job_id=job_id,
                input_path=input_path,
                output_dir=output_dir,
                variations=variations,
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
    ) -> None:
        await self._repository.set_job_status(job_id, JobStatus.RUNNING)

        async def on_result(result: VariationResult) -> None:
            await self._repository.set_variation_result(
                job_id=job_id,
                variation_id=result.variation_id,
                status=result.status.value,
                error=result.error,
                size_bytes=result.size_bytes,
            )

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
            )
        except asyncio.CancelledError:
            # As variações que não chegaram a rodar ficariam eternamente
            # "na fila" na tela do usuário se não fossem encerradas aqui.
            await self._repository.fail_unfinished_variations(
                job_id, "Cancelado antes de terminar."
            )
            await self._repository.set_job_status(job_id, JobStatus.CANCELLED)
            raise
        except Exception:
            logger.exception("Falha ao processar o job %s", job_id)
            await self._repository.set_job_status(
                job_id,
                JobStatus.FAILED,
                "Não foi possível processar o vídeo enviado.",
            )
            return

        succeeded = any(
            result.status is VariationStatus.COMPLETED for result in results
        )
        if succeeded:
            await self._repository.set_job_status(job_id, JobStatus.COMPLETED)
        else:
            await self._repository.set_job_status(
                job_id,
                JobStatus.FAILED,
                "Nenhuma variação pôde ser gerada a partir deste vídeo.",
            )

        # O arquivo enviado não é mais necessário depois da renderização.
        await asyncio.to_thread(input_path.unlink, True)
