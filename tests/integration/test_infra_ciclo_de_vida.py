"""Ciclo de vida do arquivo de entrada e reconciliação disco/banco.

O vídeo enviado é o maior arquivo isolado do job. Ele precisa sumir em
QUALQUER desfecho — concluído, falho ou cancelado. A parte de reconciliação
cobre o cenário de crash no meio de uma limpeza, que antes deixava lixo
permanente: diretório sem registro no banco e registro sem diretório.
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from typing import Any

import pytest

from ads_varietor.api import maintenance
from ads_varietor.api.repository import JobRepository, JobStatus
from ads_varietor.api.runner import JobRunner
from ads_varietor.core.models import VariationParams
from ads_varietor.core.probe import find_binary
from ads_varietor.settings import Settings

TIMEOUT_POLL_SEGUNDOS = 60.0
INTERVALO_POLL_SEGUNDOS = 0.02


# --- Fixtures ------------------------------------------------------------


def _gerar_video(destino: Path, *, duracao: float = 1.0) -> Path:
    subprocess.run(
        [
            find_binary("ffmpeg"), "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"testsrc=s=160x120:r=12:d={duracao}",
            "-f", "lavfi", "-i", f"sine=f=440:d={duracao}",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", "-y", str(destino),
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )
    return destino


@pytest.fixture(scope="session")
def video_curto(tmp_path_factory: pytest.TempPathFactory) -> Path:
    diretorio = tmp_path_factory.mktemp("fixtures-ciclo")
    return _gerar_video(diretorio / "entrada.mp4")


@pytest.fixture(scope="session")
def video_longo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Vídeo longo o bastante para o cancelamento pegar o job renderizando."""
    diretorio = tmp_path_factory.mktemp("fixtures-ciclo-longo")
    return _gerar_video(diretorio / "longo.mp4", duracao=25.0)


@pytest.fixture
def settings_tmp(tmp_path: Path) -> Settings:
    settings = Settings(
        storage_dir=tmp_path / "storage",
        max_concurrent_ffmpeg=1,
        ffmpeg_timeout_seconds=120,
        api_keys="",
    )
    settings.ensure_directories()
    return settings


@pytest.fixture
async def repositorio(settings_tmp: Settings) -> JobRepository:
    repository = JobRepository(settings_tmp.database_path)
    await repository.initialize()
    return repository


@pytest.fixture
def runner(repositorio: JobRepository, settings_tmp: Settings) -> JobRunner:
    return JobRunner(repository=repositorio, settings=settings_tmp)


def _params(variation_id: str) -> VariationParams:
    return VariationParams(
        variation_id=variation_id,
        metadata_title="titulo",
        metadata_author="autor",
        speed=1.0,
        video_scale=1.02,
        background_color="000000",
    )


async def _preparar_job(
    *,
    repository: JobRepository,
    settings: Settings,
    job_id: str,
    conteudo: bytes,
    variacoes: list[VariationParams],
    api_key_hash: str = "hash-de-teste",
) -> tuple[Path, Path]:
    upload_path = settings.uploads_dir / f"{job_id}.mp4"
    upload_path.write_bytes(conteudo)
    output_dir = settings.jobs_dir / job_id
    await repository.create_job(
        job_id=job_id,
        api_key_hash=api_key_hash,
        num_variations=len(variacoes),
        input_path=upload_path,
        input_bytes=len(conteudo),
        output_dir=output_dir,
        variations=[
            (item.variation_id, item.model_dump(mode="json"))
            for item in variacoes
        ],
    )
    return upload_path, output_dir


async def _esperar(
    condicao: Any, *, timeout: float = TIMEOUT_POLL_SEGUNDOS
) -> Any:
    loop = asyncio.get_running_loop()
    limite = loop.time() + timeout
    while loop.time() < limite:
        valor = await condicao()
        if valor:
            return valor
        await asyncio.sleep(INTERVALO_POLL_SEGUNDOS)
    raise AssertionError("condição não satisfeita dentro do tempo limite")


async def _esperar_terminal(
    repository: JobRepository, job_id: str
) -> dict[str, Any]:
    async def _pronto() -> dict[str, Any] | None:
        job = await repository.get_job(job_id)
        if job is not None and JobStatus(job["status"]).is_terminal:
            return job
        return None

    return await _esperar(_pronto)


# --- Entrada apagada em qualquer desfecho --------------------------------


async def test_entrada_e_apagada_quando_o_job_falha(
    runner: JobRunner, repositorio: JobRepository, settings_tmp: Settings
) -> None:
    """Job que falha no probe também precisa liberar o vídeo enviado.

    Antes, só o caminho feliz apagava a entrada: o arquivo de um job falho
    ficava ocupando disco até o fim do período de retenção.
    """
    variacoes = [_params("var_01")]
    upload_path, output_dir = await _preparar_job(
        repository=repositorio,
        settings=settings_tmp,
        job_id="job_falho",
        conteudo=b"isto nao e um video" * 64,
        variacoes=variacoes,
    )
    assert upload_path.is_file()

    runner.start(
        job_id="job_falho",
        input_path=upload_path,
        output_dir=output_dir,
        variations=variacoes,
    )

    job = await _esperar_terminal(repositorio, "job_falho")
    assert job["status"] == JobStatus.FAILED.value
    assert not upload_path.exists()


async def test_entrada_e_apagada_quando_o_job_e_cancelado(
    runner: JobRunner,
    repositorio: JobRepository,
    settings_tmp: Settings,
    video_longo: Path,
) -> None:
    variacoes = [_params("var_01"), _params("var_02")]
    upload_path, output_dir = await _preparar_job(
        repository=repositorio,
        settings=settings_tmp,
        job_id="job_cancelado",
        conteudo=video_longo.read_bytes(),
        variacoes=variacoes,
    )

    runner.start(
        job_id="job_cancelado",
        input_path=upload_path,
        output_dir=output_dir,
        variations=variacoes,
    )

    async def _comecou() -> bool:
        job = await repositorio.get_job("job_cancelado")
        return job is not None and job["status"] == JobStatus.RUNNING.value

    await _esperar(_comecou, timeout=30.0)
    assert await runner.cancel("job_cancelado") is True

    job = await repositorio.get_job("job_cancelado")
    assert job is not None
    assert job["status"] == JobStatus.CANCELLED.value
    assert not upload_path.exists()


async def test_entrada_continua_apagada_quando_o_job_conclui(
    runner: JobRunner,
    repositorio: JobRepository,
    settings_tmp: Settings,
    video_curto: Path,
) -> None:
    """Regressão do caminho feliz: o `finally` não pode ter quebrado ele."""
    variacoes = [_params("var_01")]
    upload_path, output_dir = await _preparar_job(
        repository=repositorio,
        settings=settings_tmp,
        job_id="job_ok",
        conteudo=video_curto.read_bytes(),
        variacoes=variacoes,
    )

    runner.start(
        job_id="job_ok",
        input_path=upload_path,
        output_dir=output_dir,
        variations=variacoes,
    )

    job = await _esperar_terminal(repositorio, "job_ok")
    assert job["status"] == JobStatus.COMPLETED.value, job["error"]
    assert not upload_path.exists()
    assert (output_dir / "var_01.mp4").is_file()


# --- Reconciliação disco x banco -----------------------------------------


async def test_reconcile_apaga_diretorio_de_job_que_nao_existe_no_banco(
    repositorio: JobRepository, settings_tmp: Settings
) -> None:
    orfao = settings_tmp.jobs_dir / "jobquesumiudobanco"
    orfao.mkdir(parents=True)
    (orfao / "var_01.mp4").write_bytes(b"lixo de um crash anterior")

    report = await maintenance.run_reconcile(repositorio, settings_tmp)

    assert report.orphan_directories == 1
    assert not orfao.exists()


async def test_reconcile_preserva_diretorio_de_job_registrado(
    repositorio: JobRepository, settings_tmp: Settings
) -> None:
    _, output_dir = await _preparar_job(
        repository=repositorio,
        settings=settings_tmp,
        job_id="jobvivo",
        conteudo=b"entrada",
        variacoes=[_params("var_01")],
    )
    output_dir.mkdir(parents=True)
    (output_dir / "var_01.mp4").write_bytes(b"saida legitima")

    report = await maintenance.run_reconcile(repositorio, settings_tmp)

    assert report.orphan_directories == 0
    assert (output_dir / "var_01.mp4").is_file()


async def test_reconcile_marca_expirado_o_job_concluido_sem_diretorio(
    repositorio: JobRepository, settings_tmp: Settings
) -> None:
    """Registro apontando para arquivos que não existem mais vira expired.

    Sem isto o cliente recebe 200 com uma lista de variações que nenhum
    download consegue entregar.
    """
    await _preparar_job(
        repository=repositorio,
        settings=settings_tmp,
        job_id="jobsemarquivos",
        conteudo=b"entrada",
        variacoes=[_params("var_01")],
    )
    await repositorio.set_job_status("jobsemarquivos", JobStatus.COMPLETED)

    report = await maintenance.run_reconcile(repositorio, settings_tmp)

    assert report.missing_directories == 1
    job = await repositorio.get_job("jobsemarquivos")
    assert job is not None
    assert job["status"] == JobStatus.EXPIRED.value


async def test_reconcile_apaga_upload_sem_job_depois_da_folga(
    repositorio: JobRepository, settings_tmp: Settings
) -> None:
    orfao = settings_tmp.uploads_dir / "sem-dono.mp4"
    orfao.write_bytes(b"upload que nunca virou job")

    settings_curto = settings_tmp.model_copy(
        update={"unreferenced_upload_grace_seconds": 1}
    )
    # A folga existe justamente para não apagar um upload recém-gravado.
    report_imediato = await maintenance.run_reconcile(repositorio, settings_tmp)
    assert report_imediato.orphan_uploads == 0
    assert orfao.is_file()

    await asyncio.sleep(1.1)
    report = await maintenance.run_reconcile(repositorio, settings_curto)

    assert report.orphan_uploads == 1
    assert not orfao.exists()


async def test_reconcile_preserva_upload_de_job_ainda_pendente(
    repositorio: JobRepository, settings_tmp: Settings
) -> None:
    upload_path, _ = await _preparar_job(
        repository=repositorio,
        settings=settings_tmp,
        job_id="jobpendente",
        conteudo=b"entrada em uso",
        variacoes=[_params("var_01")],
    )

    settings_sem_folga = settings_tmp.model_copy(
        update={"unreferenced_upload_grace_seconds": 1}
    )
    await asyncio.sleep(1.1)
    report = await maintenance.run_reconcile(repositorio, settings_sem_folga)

    assert report.orphan_uploads == 0
    assert upload_path.is_file()


async def test_reconcile_nao_reporta_nada_quando_disco_e_banco_batem(
    repositorio: JobRepository, settings_tmp: Settings
) -> None:
    report = await maintenance.run_reconcile(repositorio, settings_tmp)

    assert report.is_empty
