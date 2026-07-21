"""Testes de integração do render com overlay e do JobRunner.

Parte 1: renderiza de verdade um vídeo base longo com um clipe de overlay
curto e confere, via ffprobe, que a saída mantém a duração do vídeo BASE.
Era esse o bug: `shortest=1` no overlay truncava a saída na duração do
clipe sobreposto.

Parte 2: exercita `api/runner.py` diretamente — ciclo de vida do job,
cancelamento (sem deixar .mp4 parcial no disco), shutdown e mensagem de
erro sanitizada para vídeo inválido.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from video_variations.api.repository import JobRepository, JobStatus
from video_variations.api.runner import JobRunner
from video_variations.core.batch import render_batch
from video_variations.core.models import (
    VariationParams,
    VariationStatus,
)
from video_variations.core.probe import find_binary
from video_variations.settings import Settings

DURACAO_BASE_SEGUNDOS = 6
DURACAO_OVERLAY_SEGUNDOS = 2
TIMEOUT_POLL_SEGUNDOS = 60.0
INTERVALO_POLL_SEGUNDOS = 0.02


# --- Helpers -------------------------------------------------------------


def _gerar_video(
    destino: Path,
    *,
    duracao: float,
    largura: int = 160,
    altura: int = 120,
    fps: int = 12,
    com_audio: bool = True,
) -> Path:
    """Gera um MP4 sintético pequeno com as fontes do lavfi."""
    comando = [
        find_binary("ffmpeg"),
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=s={largura}x{altura}:r={fps}:d={duracao}",
    ]
    if com_audio:
        comando += ["-f", "lavfi", "-i", f"sine=f=440:d={duracao}"]
    comando += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]
    if com_audio:
        comando += ["-c:a", "aac", "-shortest"]
    comando += ["-y", str(destino)]
    subprocess.run(comando, check=True, capture_output=True, timeout=120)
    return destino


def _duracao_ffprobe(path: Path) -> float:
    """Lê a duração real do container com ffprobe."""
    saida = subprocess.run(
        [
            find_binary("ffprobe"),
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )
    return float(json.loads(saida.stdout)["format"]["duration"])


def _arquivo_e_video_legivel(path: Path) -> bool:
    """True se o ffprobe consegue ler o arquivo como vídeo íntegro."""
    resultado = subprocess.run(
        [
            find_binary("ffprobe"),
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name",
            "-print_format",
            "json",
            str(path),
        ],
        capture_output=True,
        timeout=60,
    )
    if resultado.returncode != 0:
        return False
    streams = json.loads(resultado.stdout).get("streams", [])
    return len(streams) == 1


def _params(variation_id: str, **overrides: Any) -> VariationParams:
    base: dict[str, Any] = {"variation_id": variation_id}
    base.update(overrides)
    return VariationParams(**base)


# --- Fixtures ------------------------------------------------------------


@pytest.fixture(scope="session")
def video_base_6s(tmp_path_factory: pytest.TempPathFactory) -> Path:
    diretorio = tmp_path_factory.mktemp("fixture-base-6s")
    return _gerar_video(
        diretorio / "base.mp4", duracao=DURACAO_BASE_SEGUNDOS, com_audio=True
    )


@pytest.fixture(scope="session")
def clipe_overlay_2s(tmp_path_factory: pytest.TempPathFactory) -> Path:
    diretorio = tmp_path_factory.mktemp("fixture-overlay-2s")
    return _gerar_video(
        diretorio / "overlay.mp4",
        duracao=DURACAO_OVERLAY_SEGUNDOS,
        largura=80,
        altura=60,
        com_audio=False,
    )


@pytest.fixture(scope="session")
def video_curto_1s(tmp_path_factory: pytest.TempPathFactory) -> Path:
    diretorio = tmp_path_factory.mktemp("fixture-curto-1s")
    return _gerar_video(diretorio / "curto.mp4", duracao=1, com_audio=True)


@pytest.fixture(scope="session")
def video_medio_4s(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Vídeo grande o bastante para dar tempo de cancelar no meio."""
    diretorio = tmp_path_factory.mktemp("fixture-medio-4s")
    return _gerar_video(
        diretorio / "medio.mp4",
        duracao=4,
        largura=640,
        altura=480,
        fps=25,
        com_audio=True,
    )


# ==========================================================================
# PARTE 1 — regressão: overlay não pode truncar a saída
# ==========================================================================


async def test_saida_mantem_duracao_do_video_base_quando_overlay_e_mais_curto(
    tmp_path: Path, video_base_6s: Path, clipe_overlay_2s: Path
) -> None:
    """O overlay de 2s não pode encurtar a saída do vídeo base de 6s."""
    saida_dir = tmp_path / "saida"
    variacao = _params(
        "var_overlay",
        overlay_enabled=True,
        overlay_opacity=0.5,
        overlay_scale=0.4,
    )

    resultados = await render_batch(
        input_video=video_base_6s,
        output_dir=saida_dir,
        variations=[variacao],
        overlay_video=clipe_overlay_2s,
        timeout_seconds=120,
    )

    assert len(resultados) == 1
    resultado = resultados[0]
    assert resultado.status is VariationStatus.COMPLETED, resultado.error

    arquivo = saida_dir / "var_overlay.mp4"
    assert arquivo.exists()

    duracao_entrada = _duracao_ffprobe(video_base_6s)
    duracao_saida = _duracao_ffprobe(arquivo)

    # O bug antigo (`shortest=1`) produzia ~2s aqui.
    assert duracao_saida > DURACAO_OVERLAY_SEGUNDOS + 1.0, (
        f"saída truncada na duração do overlay: {duracao_saida:.2f}s"
    )
    assert duracao_saida >= 5.0, f"saída com {duracao_saida:.2f}s"
    assert abs(duracao_saida - duracao_entrada) <= 1.0, (
        f"entrada {duracao_entrada:.2f}s vs saída {duracao_saida:.2f}s"
    )


async def test_overlay_nao_altera_duracao_quando_desabilitado_na_variacao(
    tmp_path: Path, video_base_6s: Path, clipe_overlay_2s: Path
) -> None:
    """Com overlay_enabled=False o clipe extra é ignorado, sem truncar nada."""
    saida_dir = tmp_path / "saida"
    resultados = await render_batch(
        input_video=video_base_6s,
        output_dir=saida_dir,
        variations=[_params("var_sem_overlay", overlay_enabled=False)],
        overlay_video=clipe_overlay_2s,
        timeout_seconds=120,
    )

    assert resultados[0].status is VariationStatus.COMPLETED, resultados[0].error
    duracao_saida = _duracao_ffprobe(saida_dir / "var_sem_overlay.mp4")
    assert duracao_saida >= 5.0, f"saída com {duracao_saida:.2f}s"


# ==========================================================================
# PARTE 2 — JobRunner
# ==========================================================================


@pytest.fixture
def settings_tmp(tmp_path: Path) -> Settings:
    """Settings apontando exclusivamente para tmp_path."""
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


async def _preparar_job(
    *,
    repository: JobRepository,
    settings: Settings,
    job_id: str,
    video_origem: Path,
    variacoes: list[VariationParams],
) -> tuple[Path, Path]:
    """Copia o vídeo para uploads/ e registra o job no banco."""
    upload_path = settings.uploads_dir / f"{job_id}.mp4"
    upload_path.write_bytes(video_origem.read_bytes())
    output_dir = settings.jobs_dir / job_id
    await repository.create_job(
        job_id=job_id,
        api_key_hash="hash-de-teste",
        num_variations=len(variacoes),
        input_path=upload_path,
        output_dir=output_dir,
        variations=[
            (item.variation_id, item.model_dump(mode="json")) for item in variacoes
        ],
    )
    return upload_path, output_dir


async def _esperar(condicao, *, timeout: float = TIMEOUT_POLL_SEGUNDOS) -> Any:
    """Espera a corrotina `condicao` devolver algo verdadeiro."""
    loop = asyncio.get_running_loop()
    limite = loop.time() + timeout
    while loop.time() < limite:
        valor = await condicao()
        if valor:
            return valor
        await asyncio.sleep(INTERVALO_POLL_SEGUNDOS)
    raise AssertionError("condição não satisfeita dentro do tempo limite")


async def _esperar_status_terminal(
    repository: JobRepository, job_id: str
) -> dict[str, Any]:
    async def _pronto() -> dict[str, Any] | None:
        job = await repository.get_job(job_id)
        if job is not None and JobStatus(job["status"]).is_terminal:
            return job
        return None

    return await _esperar(_pronto)


async def test_job_chega_a_completed_no_repositorio_quando_runner_inicia(
    runner: JobRunner,
    repositorio: JobRepository,
    settings_tmp: Settings,
    video_curto_1s: Path,
) -> None:
    variacoes = [_params("var_01"), _params("var_02", speed=1.5)]
    upload_path, output_dir = await _preparar_job(
        repository=repositorio,
        settings=settings_tmp,
        job_id="job_ok",
        video_origem=video_curto_1s,
        variacoes=variacoes,
    )

    runner.start(
        job_id="job_ok",
        input_path=upload_path,
        output_dir=output_dir,
        variations=variacoes,
    )

    job = await _esperar_status_terminal(repositorio, "job_ok")
    assert job["status"] == JobStatus.COMPLETED.value, job["error"]
    assert {item["status"] for item in job["variations"]} == {"completed"}
    assert sorted(path.name for path in output_dir.glob("*.mp4")) == [
        "var_01.mp4",
        "var_02.mp4",
    ]


async def test_arquivo_de_upload_e_removido_quando_job_conclui(
    runner: JobRunner,
    repositorio: JobRepository,
    settings_tmp: Settings,
    video_curto_1s: Path,
) -> None:
    variacoes = [_params("var_01")]
    upload_path, output_dir = await _preparar_job(
        repository=repositorio,
        settings=settings_tmp,
        job_id="job_limpeza",
        video_origem=video_curto_1s,
        variacoes=variacoes,
    )
    assert upload_path.exists()

    runner.start(
        job_id="job_limpeza",
        input_path=upload_path,
        output_dir=output_dir,
        variations=variacoes,
    )
    await _esperar_status_terminal(repositorio, "job_limpeza")

    async def _sumiu() -> bool:
        return not upload_path.exists()

    await _esperar(_sumiu, timeout=10.0)
    assert not upload_path.exists()
    # A saída renderizada permanece: só o upload é descartado.
    assert (output_dir / "var_01.mp4").exists()


async def test_cancel_marca_cancelled_e_nao_deixa_mp4_parcial_no_disco(
    runner: JobRunner,
    repositorio: JobRepository,
    settings_tmp: Settings,
    video_medio_4s: Path,
) -> None:
    """Cancelar no meio não pode deixar arquivo truncado na saída."""
    variacoes = [_params(f"var_{indice:02d}") for indice in range(6)]
    upload_path, output_dir = await _preparar_job(
        repository=repositorio,
        settings=settings_tmp,
        job_id="job_cancel",
        video_origem=video_medio_4s,
        variacoes=variacoes,
    )

    runner.start(
        job_id="job_cancel",
        input_path=upload_path,
        output_dir=output_dir,
        variations=variacoes,
    )

    # Espera o FFmpeg abrir o primeiro arquivo de saída para cancelar com um
    # encode realmente em andamento.
    async def _comecou_a_escrever() -> bool:
        return output_dir.is_dir() and any(output_dir.glob("*.mp4"))

    await _esperar(_comecou_a_escrever, timeout=30.0)

    assert await runner.cancel("job_cancel") is True

    job = await repositorio.get_job("job_cancel")
    assert job is not None
    assert job["status"] == JobStatus.CANCELLED.value

    concluidas = {
        item["variation_id"]
        for item in job["variations"]
        if item["status"] == "completed"
    }
    nao_concluidas = [
        item for item in job["variations"] if item["status"] != "completed"
    ]
    assert nao_concluidas, "o job terminou sozinho antes do cancelamento"
    assert all(item["status"] == "failed" for item in nao_concluidas), [
        item["status"] for item in nao_concluidas
    ]

    arquivos = sorted(path.name for path in output_dir.glob("*.mp4"))
    esperados = sorted(f"{item}.mp4" for item in concluidas)
    assert arquivos == esperados, (
        f"sobrou .mp4 parcial na saída: {set(arquivos) - set(esperados)}"
    )
    for nome in arquivos:
        assert _arquivo_e_video_legivel(output_dir / nome), (
            f"{nome} ficou corrompido depois do cancelamento"
        )


async def test_cancel_devolve_false_quando_job_nao_existe(
    runner: JobRunner,
) -> None:
    assert await runner.cancel("job_que_nunca_existiu") is False


async def test_cancel_devolve_false_quando_job_ja_terminou(
    runner: JobRunner,
    repositorio: JobRepository,
    settings_tmp: Settings,
    video_curto_1s: Path,
) -> None:
    variacoes = [_params("var_01")]
    upload_path, output_dir = await _preparar_job(
        repository=repositorio,
        settings=settings_tmp,
        job_id="job_terminado",
        video_origem=video_curto_1s,
        variacoes=variacoes,
    )
    runner.start(
        job_id="job_terminado",
        input_path=upload_path,
        output_dir=output_dir,
        variations=variacoes,
    )
    job = await _esperar_status_terminal(repositorio, "job_terminado")
    assert job["status"] == JobStatus.COMPLETED.value

    assert await runner.cancel("job_terminado") is False
    # O cancelamento tardio não pode reescrever o estado terminal.
    depois = await repositorio.get_job("job_terminado")
    assert depois is not None
    assert depois["status"] == JobStatus.COMPLETED.value


async def test_shutdown_cancela_todos_os_jobs_em_andamento(
    runner: JobRunner,
    repositorio: JobRepository,
    settings_tmp: Settings,
    video_medio_4s: Path,
) -> None:
    ids = ("job_a", "job_b")
    for job_id in ids:
        variacoes = [_params(f"var_{indice:02d}") for indice in range(4)]
        upload_path, output_dir = await _preparar_job(
            repository=repositorio,
            settings=settings_tmp,
            job_id=job_id,
            video_origem=video_medio_4s,
            variacoes=variacoes,
        )
        runner.start(
            job_id=job_id,
            input_path=upload_path,
            output_dir=output_dir,
            variations=variacoes,
        )

    async def _ambos_rodando() -> bool:
        for job_id in ids:
            job = await repositorio.get_job(job_id)
            if job is None or job["status"] != JobStatus.RUNNING.value:
                return False
        return True

    await _esperar(_ambos_rodando, timeout=30.0)

    await runner.shutdown()

    for job_id in ids:
        job = await repositorio.get_job(job_id)
        assert job is not None
        assert job["status"] == JobStatus.CANCELLED.value, job_id

    # Nada pode continuar registrado como em andamento depois do shutdown.
    assert await runner.cancel("job_a") is False
    assert await runner.cancel("job_b") is False


async def test_job_falha_com_mensagem_sanitizada_quando_video_e_invalido(
    runner: JobRunner,
    repositorio: JobRepository,
    settings_tmp: Settings,
) -> None:
    """Erro exposto não pode vazar caminho de disco nem saída do FFmpeg."""
    variacoes = [_params("var_01")]
    upload_path = settings_tmp.uploads_dir / "job_invalido.mp4"
    upload_path.write_bytes(b"isto nao e um video, e so texto qualquer" * 32)
    output_dir = settings_tmp.jobs_dir / "job_invalido"
    await repositorio.create_job(
        job_id="job_invalido",
        api_key_hash="hash-de-teste",
        num_variations=1,
        input_path=upload_path,
        output_dir=output_dir,
        variations=[
            (item.variation_id, item.model_dump(mode="json")) for item in variacoes
        ],
    )

    runner.start(
        job_id="job_invalido",
        input_path=upload_path,
        output_dir=output_dir,
        variations=variacoes,
    )

    job = await _esperar_status_terminal(repositorio, "job_invalido")
    assert job["status"] == JobStatus.FAILED.value

    mensagem = job["error"] or ""
    assert mensagem, "job falho precisa explicar o motivo ao usuário"
    assert str(settings_tmp.storage_dir) not in mensagem
    assert str(upload_path) not in mensagem
    assert "/" not in mensagem
    for termo in ("ffprobe", "ffmpeg", "Invalid data", "moov atom", "Traceback"):
        assert termo.lower() not in mensagem.lower(), termo
    assert not list(output_dir.glob("*.mp4")) if output_dir.is_dir() else True
