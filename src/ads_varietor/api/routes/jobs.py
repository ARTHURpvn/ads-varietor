"""Rotas de criação, consulta, cancelamento e download de jobs."""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, Request, Response, UploadFile, status
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from ads_varietor.api import errors, maintenance, storage
from ads_varietor.api.observability import log_event, owner_id
from ads_varietor.api.deps import (
    AppSettings,
    JobCreationKey,
    RateLimitedKey,
    Repository,
)
from ads_varietor.api.repository import JobStatus
from ads_varietor.api.runner import JobRunner
from ads_varietor.api.schemas import (
    JobCreatedResponse,
    JobDetailResponse,
    JobProgress,
    VariationView,
)
from ads_varietor.core.ffmpeg import compute_md5
from ads_varietor.core.generator import VariationGenerator
from ads_varietor.core.models import EffectSelection, ProcessingMode
from ads_varietor.core.probe import InvalidVideoError, probe_video

logger = logging.getLogger(__name__)

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


async def _enforce_key_quota(
    *,
    repository: Repository,
    settings: AppSettings,
    api_key_hash: str,
    input_path: Path,
    input_bytes: int,
    num_variations: int,
) -> None:
    """Rejeita o job se a chave já estourou a própria quota de disco.

    A quota global sozinha não protege ninguém: uma chave que enche o disco
    trava todas as outras. O erro distingue "serviço lotado" de "seu limite"
    e não menciona consumo de terceiros.
    """
    usados = await repository.bytes_used_by_key(api_key_hash)
    reserva = input_bytes * (1 + num_variations)

    if usados + reserva <= settings.max_storage_bytes_per_key:
        return

    await storage.remove_path(input_path)
    log_event(
        logger,
        "quota.key_exceeded",
        level=logging.WARNING,
        owner=owner_id(api_key_hash),
        bytes_total=usados,
        reserved_bytes=reserva,
        quota_bytes=settings.max_storage_bytes_per_key,
    )
    raise errors.key_quota_exceeded(settings.max_storage_bytes_per_key)


def _to_detail_response(job: dict[str, Any]) -> JobDetailResponse:
    variations = job["variations"]
    completed = sum(1 for item in variations if item["status"] == "completed")
    failed = sum(1 for item in variations if item["status"] == "failed")

    # O total é a média do andamento de cada variação, e não a contagem de
    # arquivos prontos: assim a barra sobe enquanto um vídeo é processado,
    # em vez de saltar só quando ele termina.
    total_variacoes = job["num_variations"] or 1
    andamento = sum(item.get("progress", 0.0) for item in variations)
    percentual = round(min(100.0, andamento / total_variacoes * 100), 1)

    return JobDetailResponse(
        job_id=job["job_id"],
        status=JobStatus(job["status"]),
        num_variations=job["num_variations"],
        mode=ProcessingMode(job["mode"]),
        source_md5=job["source_md5"],
        created_at=job["created_at"],
        updated_at=job["updated_at"],
        error=job["error"],
        progress=JobProgress(
            total=job["num_variations"],
            completed=completed,
            failed=failed,
            percent=percentual,
        ),
        variations=[
            VariationView.model_validate(
                {**item, "progress": round(item.get("progress", 0.0) * 100, 1)}
            )
            for item in variations
        ],
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
    mode: Annotated[ProcessingMode, Form()] = ProcessingMode.FULL,
    effect_color: Annotated[bool, Form()] = True,
    effect_framing: Annotated[bool, Form()] = True,
    effect_speed: Annotated[bool, Form()] = True,
    effect_noise: Annotated[bool, Form()] = True,
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

    efeitos = EffectSelection(
        color=effect_color,
        framing=effect_framing,
        speed=effect_speed,
        noise=effect_noise,
    )
    # No modo completo, desligar tudo deixaria a imagem idêntica à origem: o
    # arquivo mudaria só nos metadados, que é justamente o que o modo rápido
    # já faz sem gastar um reencode. Barrar aqui evita o usuário pagar caro
    # por um resultado que ele consegue de graça.
    if mode is ProcessingMode.FULL and efeitos.nenhum():
        raise errors.ProblemError(
            status=400,
            title="Nenhum efeito selecionado",
            detail=(
                "Escolha ao menos um efeito para gerar variações, ou use o "
                "modo que só troca a identidade do arquivo."
            ),
        )

    # A reserva considera a entrada mais as N variações que serão gravadas.
    # Contar só o upload subestimava o consumo real em uma ordem de grandeza.
    used_bytes = await storage.get_used_bytes(settings.storage_dir)
    reserva = settings.max_upload_bytes * (1 + num_variations)
    if used_bytes + reserva > settings.max_storage_bytes:
        raise errors.storage_full()

    try:
        input_path, input_bytes = await storage.save_upload(
            file, settings.uploads_dir, max_bytes=settings.max_upload_bytes
        )
    except storage.UploadTooLargeError:
        raise errors.upload_too_large(settings.max_upload_bytes) from None

    # Com o arquivo em disco o tamanho real é conhecido, então a reserva por
    # chave usa a entrada de verdade em vez do teto de upload. Antes disso
    # só dava para estimar pelo pior caso, o que rejeitaria job legítimo.
    await _enforce_key_quota(
        repository=repository,
        settings=settings,
        api_key_hash=api_key_hash,
        input_path=input_path,
        input_bytes=input_bytes,
        num_variations=num_variations,
    )

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
    variations = VariationGenerator().generate(num_variations, effects=efeitos)
    # Guardado para o cliente poder comparar o hash de origem com o de cada
    # saída e confirmar que nenhum arquivo repete o original.
    source_md5 = await asyncio.to_thread(compute_md5, input_path)

    try:
        await repository.create_job(
            job_id=job_id,
            api_key_hash=api_key_hash,
            num_variations=num_variations,
            mode=mode.value,
            source_md5=source_md5,
            input_bytes=input_bytes,
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

    dono = owner_id(api_key_hash)
    log_event(
        logger,
        "job.created",
        job_id=job_id,
        owner=dono,
        bytes_total=input_bytes,
        num_variations=num_variations,
        mode=mode.value,
    )

    _get_runner(request).start(
        job_id=job_id,
        input_path=input_path,
        output_dir=output_dir,
        variations=variations,
        mode=mode,
        owner=dono,
    )

    job = await repository.get_job(job_id)
    assert job is not None
    return JobCreatedResponse(
        job_id=job_id,
        status=JobStatus.PENDING,
        num_variations=num_variations,
        mode=mode,
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
            # O job ainda não tinha task viva (pendente ou já removida): o
            # arquivo de entrada continuaria em disco sem ninguém para
            # apagá-lo, então a limpeza acontece aqui.
            await repository.set_job_status(job_id, JobStatus.CANCELLED)
            await storage.remove_path(Path(job["input_path"]))
            log_event(
                logger,
                "job.cancelled",
                job_id=job_id,
                owner=owner_id(api_key_hash),
            )

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

    async def _apos_o_envio() -> None:
        # O ZIP é derivado: apagar depois do envio evita dobrar o espaço
        # ocupado por cada job no disco.
        archive_path.unlink(missing_ok=True)
        if not settings.delete_after_batch_download:
            return
        await maintenance.purge_job_files(job)
        await repository.mark_expired(job_id)
        log_event(
            logger,
            "job.purged_after_download",
            job_id=job_id,
            owner=owner_id(api_key_hash),
            bytes_total=total_bytes,
        )

    return FileResponse(
        archive_path,
        media_type="application/zip",
        filename=f"variacoes_{job_id}.zip",
        background=BackgroundTask(_apos_o_envio),
    )
