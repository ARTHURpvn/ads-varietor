"""Gravação e leitura dos arquivos de vídeo em disco.

Nenhum nome de arquivo enviado pelo usuário chega ao filesystem: o upload é
salvo com um UUID e uma extensão de uma lista fixa.
"""

from __future__ import annotations

import asyncio
import re
import shutil
import time
import uuid
import zipfile
from pathlib import Path
from typing import Protocol

ALLOWED_EXTENSIONS = frozenset({".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"})
DEFAULT_EXTENSION = ".mp4"
CHUNK_SIZE = 1024 * 1024
# `\Z` e não `$`: em Python, `$` também casa antes de um \n final, então o
# padrão com `$` aceitaria "job\n" como identificador válido.
SAFE_IDENTIFIER = re.compile(r"\A[A-Za-z0-9_-]{1,64}\Z")


class UploadTooLargeError(ValueError):
    """O upload excedeu o tamanho máximo permitido."""


class PathTraversalError(ValueError):
    """O caminho resolvido escapa do diretório permitido."""


class AsyncUploadFile(Protocol):
    """Interface mínima do UploadFile do Starlette, para permitir teste."""

    filename: str | None

    async def read(self, size: int = -1) -> bytes: ...


def normalize_extension(filename: str | None) -> str:
    """Extrai uma extensão segura do nome enviado.

    O nome original é descartado; só a extensão é aproveitada, e apenas se
    estiver na allowlist. Isso impede que o nome influencie o caminho final.
    """
    if not filename:
        return DEFAULT_EXTENSION
    suffix = Path(filename).suffix.lower()
    return suffix if suffix in ALLOWED_EXTENSIONS else DEFAULT_EXTENSION


def is_safe_identifier(value: str) -> bool:
    """Diz se o valor serve como identificador de job ou variação."""
    return bool(SAFE_IDENTIFIER.match(value))


def resolve_within(base_dir: Path, *parts: str) -> Path:
    """Resolve um caminho garantindo que ele fique dentro de `base_dir`.

    A contenção é verificada depois de resolver o caminho, então `..`,
    caminho absoluto e link simbólico são todos pegos aqui — sem depender
    de o chamador ter validado o formato antes.
    """
    for part in parts:
        if not part or part in {".", ".."} or "/" in part or "\\" in part:
            raise PathTraversalError(f"Componente de caminho inválido: {part!r}")

    base_resolved = base_dir.resolve()
    candidate = base_resolved.joinpath(*parts).resolve()
    if candidate != base_resolved and base_resolved not in candidate.parents:
        raise PathTraversalError("Caminho fora do diretório permitido.")
    return candidate


async def save_upload(
    upload: AsyncUploadFile, destination_dir: Path, *, max_bytes: int
) -> tuple[Path, int]:
    """Grava o upload em disco em blocos, abortando se exceder o limite.

    A leitura é incremental de propósito: carregar o arquivo inteiro em
    memória permitiria derrubar o serviço com um upload grande.
    """
    destination_dir.mkdir(parents=True, exist_ok=True)
    extension = normalize_extension(upload.filename)
    destination = destination_dir / f"{uuid.uuid4().hex}{extension}"

    written = 0
    try:
        with destination.open("wb") as target:
            while True:
                chunk = await upload.read(CHUNK_SIZE)
                if not chunk:
                    break
                written += len(chunk)
                if written > max_bytes:
                    raise UploadTooLargeError(
                        f"Arquivo maior que o limite de {max_bytes} bytes."
                    )
                target.write(chunk)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise

    return destination, written


def _directory_size(path: Path) -> int:
    if not path.exists():
        return 0

    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            # A rotina de limpeza e o próprio FFmpeg mexem nestes diretórios
            # o tempo todo: um arquivo pode sumir entre o is_file e o stat.
            # Ignorar o que desapareceu é mais correto que abortar a soma.
            continue
    return total


async def get_used_bytes(storage_dir: Path) -> int:
    """Soma o espaço ocupado pelo armazenamento do serviço."""
    return await asyncio.to_thread(_directory_size, storage_dir)


def _remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)


async def remove_path(path: Path) -> None:
    """Remove um arquivo ou diretório do armazenamento do serviço."""
    await asyncio.to_thread(_remove_path, path)


def _list_job_directories(jobs_dir: Path) -> list[Path]:
    if not jobs_dir.is_dir():
        return []
    return [item for item in jobs_dir.iterdir() if item.is_dir()]


async def list_job_directories(jobs_dir: Path) -> list[Path]:
    """Diretórios de saída existentes em disco, um por job."""
    return await asyncio.to_thread(_list_job_directories, jobs_dir)


def _remove_unreferenced_uploads(
    uploads_dir: Path, referenced: frozenset[str], min_age_seconds: int
) -> int:
    if not uploads_dir.is_dir():
        return 0

    limite = time.time() - min_age_seconds
    removidos = 0
    for item in uploads_dir.iterdir():
        if not item.is_file() or str(item) in referenced:
            continue
        # A folga de idade evita apagar um upload que acabou de ser gravado
        # e ainda não virou registro no banco.
        if item.stat().st_mtime < limite:
            item.unlink(missing_ok=True)
            removidos += 1
    return removidos


async def remove_unreferenced_uploads(
    uploads_dir: Path,
    referenced: frozenset[str],
    *,
    min_age_seconds: int,
) -> int:
    """Apaga uploads que nenhum job ativo reivindica e já passaram da folga."""
    return await asyncio.to_thread(
        _remove_unreferenced_uploads, uploads_dir, referenced, min_age_seconds
    )


def _write_zip(directory: Path, filenames: list[str], target: Path) -> None:
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in filenames:
            item = directory / name
            if item.is_file():
                archive.write(item, arcname=name)


async def build_zip_file(
    directory: Path, filenames: list[str], destination: Path
) -> Path:
    """Escreve num arquivo temporário um ZIP com os arquivos indicados.

    O ZIP vai para disco, e não para a memória: um job de 50 variações pode
    somar vários GB, e montar isso num buffer derrubaria o processo. A
    escrita roda em thread para não travar o event loop — com um único
    worker, um bloqueio aqui congela todas as outras requisições.

    Só os arquivos passados em `filenames` entram; varrer o diretório
    incluiria saídas parciais de renderizações que falharam.
    """
    await asyncio.to_thread(_write_zip, directory, filenames, destination)
    return destination


def total_size_of(directory: Path, filenames: list[str]) -> int:
    """Soma o tamanho dos arquivos indicados dentro do diretório."""
    total = 0
    for name in filenames:
        item = directory / name
        if item.is_file():
            total += item.stat().st_size
    return total
