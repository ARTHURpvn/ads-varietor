"""Rotas de criação, consulta, cancelamento e download de jobs."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, Request, Response, UploadFile, status
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from video_variations.api import errors, storage
from video_variations.api.deps import (
    AppSettings,
    JobCreationKey,
    RateLimitedKey,
    Repository,
)
from video_variations.api.repository import JobStatus
from video_variations.api.runner import JobRunner
from video_variations.api.schemas import (
    JobCreatedResponse,
    JobDetailResponse,
    JobProgress,
    VariationView,
)
from video_variations.core.generator import VariationGenerator
from video_variations.core.probe import InvalidVideoError, probe_video

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _get_runner(request: Request) -> JobRunner:
    runner = getattr(request.app.state, "runner", None)
    if runner is None:  # pragma: no cover - só ocorre fora do lifespan
        raise RuntimeError("Runner não inicializado.")
    return runner


async def _load_owned_job(
    repository: Repository, job_id: str, api_key_hash: str
) -> dict[str, Any]:
    """Carrega um job garantindo que ele pertence à chave que pediu.

    Job de outra chave devolve 404, não 403: responder 403 confirmaria a
    existência do job para quem não deveria saber.
    """
    if not storage.is_safe_identifier(job_id):
        raise errors.invalid_identifier()

    job = await repository.get_job(job_id)
    if job is None or job["api_key_hash"] != api_key_hash:
        raise errors.job_not_found()
    return job


def _to_detail_response(job: dict[str, Any]) -> JobDetailResponse:
    variations = job["variations"]
    completed = sum(1 for item in variations if item["status"] == "completed")
    failed = sum(1 for item in variations if item["status"] == "failed")

    return JobDetailResponse(
        job_id=job["job_id"],
        status=JobStatus(job["status"]),
        num_variations=job["num_variations"],
        created_at=job["created_at"],
        updated_at=job["updated_at"],
        error=job["error"],
        progress=JobProgress(
            total=job["num_variations"], completed=completed, failed=failed
        ),
        variations=[VariationView.model_validate(item) for item in variations],
    )


@router.post(
    "",
    response_model=JobCreatedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Cria um job de geração de variações",
)
async def create_job(
    request: Request,
    api_key_hash: JobCreationKey,
    repository: Repository,
    settings: AppSettings,
    file: Annotated[UploadFile, File(description="Vídeo de entrada")],
    num_variations: Annotated[int, Form(ge=1)] = 5,
) -> JobCreatedResponse:
    if num_variations > settings.max_variations_per_job:
        raise errors.ProblemError(
            status=400,
            title="Quantidade inválida",
            detail=(
                "O número máximo de variações por job é "
                f"{settings.max_variations_per_job}."
            ),
        )

    # A reserva considera a entrada mais as N variações que serão gravadas.
    # Contar só o upload subestimava o consumo real em uma ordem de grandeza.
    used_bytes = await storage.get_used_bytes(settings.storage_dir)
    reserva = settings.max_upload_bytes * (1 + num_variations)
    if used_bytes + reserva > settings.max_storage_bytes:
        raise errors.storage_full()

    try:
        input_path, _ = await storage.save_upload(
            file, settings.uploads_dir, max_bytes=settings.max_upload_bytes
        )
    except storage.UploadTooLargeError:
        raise errors.upload_too_large(settings.max_upload_bytes) from None

    # Extensão e Content-Type não provam nada: só o ffprobe confirma que o
    # arquivo é mesmo um vídeo decodificável.
    try:
        info = await probe_video(input_path)
    except InvalidVideoError:
        await storage.remove_path(input_path)
        raise errors.invalid_video() from None

    # O filtergraph aloca um canvas do tamanho do vídeo: sem teto, um arquivo
    # pequeno com resolução declarada absurda esgota a memória do processo.
    if (
        info.width * info.height > settings.max_input_pixels
        or info.duration_seconds > settings.max_input_duration_seconds
    ):
        await storage.remove_path(input_path)
        raise errors.video_too_big()

    job_id = uuid.uuid4().hex
    output_dir = storage.resolve_within(settings.jobs_dir, job_id)
    variations = VariationGenerator().generate(num_variations)

    try:
        await repository.create_job(
            job_id=job_id,
            api_key_hash=api_key_hash,
            num_variations=num_variations,
            input_path=input_path,
            output_dir=output_dir,
            variations=[
                (item.variation_id, item.model_dump(mode="json"))
                for item in variations
            ],
        )
    except Exception:
        # Sem isto o upload ficaria órfão no disco para sempre: nenhuma
        # rotina de limpeza conhece um arquivo que não tem job associado.
        await storage.remove_path(input_path)
        raise

    _get_runner(request).start(
        job_id=job_id,
        input_path=input_path,
        output_dir=output_dir,
        variations=variations,
    )

    job = await repository.get_job(job_id)
    assert job is not None
    return JobCreatedResponse(
        job_id=job_id,
        status=JobStatus.PENDING,
        num_variations=num_variations,
        created_at=job["created_at"],
    )


@router.get(
    "/{job_id}",
    response_model=JobDetailResponse,
    summary="Consulta o estado de um job",
)
async def get_job(
    job_id: str,
    api_key_hash: RateLimitedKey,
    repository: Repository,
    response: Response,
) -> JobDetailResponse:
    job = await _load_owned_job(repository, job_id, api_key_hash)
    response.headers["Cache-Control"] = "no-store"
    return _to_detail_response(job)


@router.delete(
    "/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cancela um job em andamento",
)
async def cancel_job(
    request: Request,
    job_id: str,
    api_key_hash: RateLimitedKey,
    repository: Repository,
) -> Response:
    job = await _load_owned_job(repository, job_id, api_key_hash)
    current_status = JobStatus(job["status"])

    if not current_status.is_terminal:
        cancelled = await _get_runner(request).cancel(job_id)
        if not cancelled:
            await repository.set_job_status(job_id, JobStatus.CANCELLED)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{job_id}/variations/{variation_id}/download",
    summary="Baixa uma variação específica",
    response_class=FileResponse,
)
async def download_variation(
    job_id: str,
    variation_id: str,
    api_key_hash: RateLimitedKey,
    repository: Repository,
) -> FileResponse:
    job = await _load_owned_job(repository, job_id, api_key_hash)

    if not storage.is_safe_identifier(variation_id):
        raise errors.invalid_identifier()

    # O nome do arquivo vem da lista de variações do próprio job, nunca
    # diretamente da URL — só um id já registrado chega ao filesystem.
    variation = next(
        (
            item
            for item in job["variations"]
            if item["variation_id"] == variation_id
        ),
        None,
    )
    if variation is None or variation["status"] != "completed":
        raise errors.job_not_found()

    try:
        file_path = storage.resolve_within(
            Path(job["output_dir"]), f"{variation['variation_id']}.mp4"
        )
    except storage.PathTraversalError:
        raise errors.invalid_identifier() from None

    if not file_path.is_file():
        raise errors.job_not_found()

    return FileResponse(
        file_path,
        media_type="video/mp4",
        filename=f"{variation_id}.mp4",
    )


@router.get(
    "/{job_id}/download",
    summary="Baixa todas as variações concluídas em um ZIP",
)
async def download_all(
    job_id: str,
    api_key_hash: RateLimitedKey,
    repository: Repository,
    settings: AppSettings,
) -> FileResponse:
    job = await _load_owned_job(repository, job_id, api_key_hash)
    output_dir = Path(job["output_dir"])

    # Só as variações concluídas entram: varrer o diretório incluiria saídas
    # parciais de renderizações que falharam, entregando arquivo corrompido.
    concluidas = [
        f"{item['variation_id']}.mp4"
        for item in job["variations"]
        if item["status"] == "completed"
    ]
    if not concluidas or not output_dir.is_dir():
        raise errors.job_not_found()

    total_bytes = await asyncio.to_thread(
        storage.total_size_of, output_dir, concluidas
    )
    if total_bytes > settings.max_zip_bytes:
        raise errors.zip_too_large()

    archive_path = output_dir / f"{job_id}.zip"
    await storage.build_zip_file(output_dir, concluidas, archive_path)

    return FileResponse(
        archive_path,
        media_type="application/zip",
        filename=f"variacoes_{job_id}.zip",
        # O ZIP é derivado: apagar depois do envio evita dobrar o espaço
        # ocupado por cada job no disco.
        background=BackgroundTask(archive_path.unlink, missing_ok=True),
    )
