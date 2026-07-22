"""Orquestração concorrente das variações de um lote."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

from ads_varietor.core.ffmpeg import DEFAULT_PRESET, render_variation
from ads_varietor.core.models import (
    ProcessingMode,
    VariationParams,
    VariationResult,
    VariationStatus,
    VideoInfo,
)
from ads_varietor.core.probe import probe_video

ProgressCallback = Callable[[VariationResult], Awaitable[None]]


async def render_batch(
    *,
    input_video: Path,
    output_dir: Path,
    variations: list[VariationParams],
    overlay_video: Path | None = None,
    max_concurrent: int = 4,
    timeout_seconds: int = 300,
    on_result: ProgressCallback | None = None,
    info: VideoInfo | None = None,
    semaphore: asyncio.Semaphore | None = None,
    mode: ProcessingMode = ProcessingMode.FULL,
    preset: str = DEFAULT_PRESET,
    threads: int = 0,
) -> list[VariationResult]:
    """Renderiza todas as variações respeitando o limite de concorrência.

    O trabalho pesado roda dentro do FFmpeg, em processos separados; o
    semáforo limita quantos existem ao mesmo tempo para não saturar a CPU.
    Quem chama pode passar um semáforo compartilhado — o serviço usa um só
    para todos os jobs, senão dez jobs simultâneos abririam dez vezes o
    limite de processos.
    `on_result` é chamado assim que cada variação termina, permitindo
    reportar progresso antes do lote inteiro acabar.
    """
    if not variations:
        return []

    output_dir.mkdir(parents=True, exist_ok=True)
    video_info = info if info is not None else await probe_video(input_video)
    limite = semaphore if semaphore is not None else asyncio.Semaphore(max_concurrent)

    async def run_one(params: VariationParams) -> VariationResult:
        async with limite:
            result = await render_variation(
                input_video=input_video,
                output_dir=output_dir,
                params=params,
                info=video_info,
                overlay_video=overlay_video,
                timeout_seconds=timeout_seconds,
                mode=mode,
                preset=preset,
                threads=threads,
            )
        if on_result is not None:
            await on_result(result)
        return result

    tasks = [asyncio.create_task(run_one(params)) for params in variations]
    try:
        # `return_exceptions` evita que a primeira falha inesperada abandone
        # as tasks irmãs ainda rodando — elas virariam processos de FFmpeg
        # órfãos, fora do alcance do cancelamento do job.
        finalizados = await asyncio.gather(*tasks, return_exceptions=True)
    except asyncio.CancelledError:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise

    resultados: list[VariationResult] = []
    for params, finalizado in zip(variations, finalizados, strict=True):
        if isinstance(finalizado, asyncio.CancelledError):
            raise finalizado
        if isinstance(finalizado, BaseException):
            resultados.append(
                VariationResult(
                    variation_id=params.variation_id,
                    status=VariationStatus.FAILED,
                    error=f"Erro inesperado ao renderizar: {finalizado}",
                )
            )
            continue
        resultados.append(finalizado)
    return resultados


def summarize(results: list[VariationResult]) -> dict[str, int]:
    """Conta quantas variações terminaram em cada estado."""
    completed = sum(1 for item in results if item.status is VariationStatus.COMPLETED)
    return {
        "total": len(results),
        "completed": completed,
        "failed": len(results) - completed,
    }
