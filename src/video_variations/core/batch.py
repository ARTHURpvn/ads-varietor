"""Orquestração concorrente das variações de um lote."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

from video_variations.core.ffmpeg import render_variation
from video_variations.core.models import (
    VariationParams,
    VariationResult,
    VariationStatus,
    VideoInfo,
)
from video_variations.core.probe import probe_video

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
) -> list[VariationResult]:
    """Renderiza todas as variações respeitando o limite de concorrência.

    O trabalho pesado roda dentro do FFmpeg, em processos separados; o
    semáforo limita quantos existem ao mesmo tempo para não saturar a CPU.
    `on_result` é chamado assim que cada variação termina, permitindo
    reportar progresso antes do lote inteiro acabar.
    """
    if not variations:
        return []

    output_dir.mkdir(parents=True, exist_ok=True)
    video_info = info if info is not None else await probe_video(input_video)
    semaphore = asyncio.Semaphore(max_concurrent)

    async def run_one(params: VariationParams) -> VariationResult:
        async with semaphore:
            result = await render_variation(
                input_video=input_video,
                output_dir=output_dir,
                params=params,
                info=video_info,
                overlay_video=overlay_video,
                timeout_seconds=timeout_seconds,
            )
        if on_result is not None:
            await on_result(result)
        return result

    tasks = [asyncio.create_task(run_one(params)) for params in variations]
    try:
        return await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


def summarize(results: list[VariationResult]) -> dict[str, int]:
    """Conta quantas variações terminaram em cada estado."""
    completed = sum(1 for item in results if item.status is VariationStatus.COMPLETED)
    return {
        "total": len(results),
        "completed": completed,
        "failed": len(results) - completed,
    }
