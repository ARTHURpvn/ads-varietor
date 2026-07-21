"""Localização dos binários do FFmpeg e inspeção de vídeos com ffprobe."""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

from ads_varietor.core.models import VideoInfo

FALLBACK_DIRECTORIES = ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin")
PROBE_TIMEOUT_SECONDS = 30


class FFmpegNotFoundError(RuntimeError):
    """FFmpeg ou ffprobe não estão disponíveis no sistema."""


class InvalidVideoError(ValueError):
    """O arquivo não pôde ser lido como vídeo."""


def find_binary(name: str) -> str:
    """Procura um binário no PATH e depois nos diretórios usuais.

    Levanta FFmpegNotFoundError com instrução de instalação se não achar.
    """
    found = shutil.which(name)
    if found:
        return found

    for directory in FALLBACK_DIRECTORIES:
        candidate = Path(directory) / name
        if candidate.is_file():
            return str(candidate)

    raise FFmpegNotFoundError(
        f"{name} não encontrado. Instale com: brew install ffmpeg (macOS) "
        f"ou apt install ffmpeg (Linux)."
    )


async def probe_video(path: Path) -> VideoInfo:
    """Extrai dimensões, duração e presença de áudio de um vídeo.

    Esta é a única validação confiável de que o arquivo é mesmo um vídeo —
    extensão e Content-Type do upload não servem como prova.
    """
    process = await asyncio.create_subprocess_exec(
        find_binary("ffprobe"),
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
        str(path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=PROBE_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError as error:
        process.kill()
        await process.wait()
        raise InvalidVideoError("Tempo esgotado ao ler o arquivo.") from error

    if process.returncode != 0:
        detail = stderr.decode("utf-8", errors="replace").strip()
        raise InvalidVideoError(f"Arquivo não reconhecido como vídeo: {detail[:200]}")

    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as error:
        raise InvalidVideoError("Resposta inválida do ffprobe.") from error

    streams = payload.get("streams", [])
    video_stream = next(
        (item for item in streams if item.get("codec_type") == "video"), None
    )
    if video_stream is None:
        raise InvalidVideoError("O arquivo não contém stream de vídeo.")

    width = int(video_stream.get("width") or 0)
    height = int(video_stream.get("height") or 0)
    if width <= 0 or height <= 0:
        raise InvalidVideoError("Não foi possível determinar a resolução do vídeo.")

    duration_raw = payload.get("format", {}).get("duration")
    try:
        duration = float(duration_raw) if duration_raw is not None else 0.0
    except (TypeError, ValueError):
        duration = 0.0

    return VideoInfo(
        width=width,
        height=height,
        duration_seconds=duration,
        has_audio=any(item.get("codec_type") == "audio" for item in streams),
        video_codec=str(video_stream.get("codec_name") or "desconhecido"),
    )
