"""Testes de integração do fluxo de jobs contra a aplicação FastAPI real.

A app é montada com storage isolado em tmp_path e exercitada via
httpx.ASGITransport, sem subir servidor HTTP.
"""

from __future__ import annotations

import asyncio
import io
import json
import re
import secrets
import subprocess
import zipfile
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from ads_varietor.api.main import create_app
from ads_varietor.settings import get_settings

POLL_INTERVAL_SECONDS = 0.25
POLL_TIMEOUT_SECONDS = 60.0
STATUS_TERMINAIS = frozenset({"completed", "failed", "cancelled", "expired"})


# --- Fixtures ------------------------------------------------------------


def _gerar_video(destino: Path, *, duracao: int = 1) -> Path:
    """Cria um MP4 pequeno com áudio usando as fontes sintéticas do FFmpeg."""
    subprocess.run(
        [
            "ffmpeg",
            "-f", "lavfi", "-i", f"testsrc=s=160x120:r=15:d={duracao}",
            "-f", "lavfi", "-i", f"sine=f=440:d={duracao}",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", "-y", str(destino),
        ],
        check=True,
        capture_output=True,
    )
    return destino


@pytest.fixture(scope="session")
def video_valido(tmp_path_factory: pytest.TempPathFactory) -> Path:
    diretorio = tmp_path_factory.mktemp("fixtures-video")
    return _gerar_video(diretorio / "entrada.mp4")


@pytest.fixture(scope="session")
def video_longo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Vídeo com duração suficiente para dar tempo de cancelar o job."""
    diretorio = tmp_path_factory.mktemp("fixtures-video-longo")
    return _gerar_video(diretorio / "longo.mp4", duracao=4)


@pytest.fixture
def api_keys() -> list[str]:
    return [secrets.token_urlsafe(32), secrets.token_urlsafe(32)]


@pytest.fixture
def ambiente(
    tmp_path: Path, api_keys: list[str], monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """Isola storage, chaves e limites; zera o cache de settings."""
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir()

    monkeypatch.setenv("STORAGE_DIR", str(storage_dir))
    monkeypatch.setenv("API_KEYS", ",".join(api_keys))
    monkeypatch.setenv("MAX_CONCURRENT_FFMPEG", "2")
    monkeypatch.setenv("RATE_LIMIT_JOBS_PER_HOUR", "500")
    monkeypatch.setenv("RATE_LIMIT_REQUESTS_PER_MINUTE", "5000")
    monkeypatch.setenv("MAX_VARIATIONS_PER_JOB", "6")
    monkeypatch.setenv("CORS_ORIGINS", "")

    get_settings.cache_clear()
    try:
        yield
    finally:
        get_settings.cache_clear()


@pytest.fixture
async def client(ambiente: None, api_keys: list[str]) -> AsyncIterator[httpx.AsyncClient]:
    """Cliente HTTP ligado à app real, com o lifespan em execução."""
    app = create_app()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
            headers={"X-API-Key": api_keys[0]},
            timeout=30.0,
        ) as http_client:
            yield http_client


# --- Helpers -------------------------------------------------------------


async def _criar_job(
    client: httpx.AsyncClient,
    video: Path,
    *,
    num_variations: int = 2,
) -> httpx.Response:
    return await client.post(
        "/api/v1/jobs",
        files={"file": (video.name, video.read_bytes(), "video/mp4")},
        data={"num_variations": str(num_variations)},
    )


async def _esperar_status(
    client: httpx.AsyncClient,
    job_id: str,
    alvos: frozenset[str],
    *,
    timeout: float = POLL_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Faz polling do GET do job até o status cair em `alvos` ou estourar."""
    limite = asyncio.get_running_loop().time() + timeout
    corpo: dict[str, Any] = {}
    while asyncio.get_running_loop().time() < limite:
        resposta = await client.get(f"/api/v1/jobs/{job_id}")
        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        if corpo["status"] in alvos:
            return corpo
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
    raise AssertionError(
        f"Job {job_id} não atingiu {sorted(alvos)} em {timeout}s. "
        f"Último estado: {json.dumps(corpo, ensure_ascii=False)}"
    )


def _duracao_do_arquivo(caminho: Path) -> float:
    saida = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(caminho),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(saida.stdout.strip())


# --- Criação e progresso -------------------------------------------------


async def test_responde_202_com_job_pendente_quando_video_e_valido(
    client: httpx.AsyncClient, video_valido: Path
) -> None:
    resposta = await _criar_job(client, video_valido, num_variations=2)

    assert resposta.status_code == 202, resposta.text
    corpo = resposta.json()
    assert corpo["status"] == "pending"
    assert corpo["num_variations"] == 2
    assert isinstance(corpo["job_id"], str) and corpo["job_id"]
    assert corpo["created_at"]


async def test_job_e_variacoes_ficam_completed_quando_processamento_termina(
    client: httpx.AsyncClient, video_valido: Path
) -> None:
    criacao = await _criar_job(client, video_valido, num_variations=2)
    job_id = criacao.json()["job_id"]

    job = await _esperar_status(client, job_id, STATUS_TERMINAIS)

    assert job["status"] == "completed", job
    assert len(job["variations"]) == 2
    assert [item["status"] for item in job["variations"]] == ["completed"] * 2


async def test_progresso_bate_com_as_variacoes_quando_job_termina(
    client: httpx.AsyncClient, video_valido: Path
) -> None:
    """O job foi criado com 3 variações de um vídeo válido: no fim, o
    progresso precisa ser exatamente 3 concluídas e 0 falhas.
    """
    criacao = await _criar_job(client, video_valido, num_variations=3)
    job_id = criacao.json()["job_id"]

    job = await _esperar_status(client, job_id, STATUS_TERMINAIS)

    assert job["status"] == "completed", job
    assert job["progress"] == {"total": 3, "completed": 3, "failed": 0}, job


# --- Downloads -----------------------------------------------------------


async def test_download_individual_devolve_mp4_valido_quando_variacao_concluiu(
    client: httpx.AsyncClient, video_valido: Path, tmp_path: Path
) -> None:
    criacao = await _criar_job(client, video_valido, num_variations=2)
    job_id = criacao.json()["job_id"]
    job = await _esperar_status(client, job_id, STATUS_TERMINAIS)
    variation_id = next(
        item["variation_id"]
        for item in job["variations"]
        if item["status"] == "completed"
    )

    resposta = await client.get(
        f"/api/v1/jobs/{job_id}/variations/{variation_id}/download"
    )

    assert resposta.status_code == 200, resposta.text
    assert resposta.headers["content-type"] == "video/mp4"
    assert len(resposta.content) > 0

    baixado = tmp_path / "baixado.mp4"
    baixado.write_bytes(resposta.content)
    assert _duracao_do_arquivo(baixado) > 0


async def test_download_em_lote_traz_zip_com_as_variacoes_concluidas(
    client: httpx.AsyncClient, video_valido: Path
) -> None:
    criacao = await _criar_job(client, video_valido, num_variations=2)
    job_id = criacao.json()["job_id"]
    job = await _esperar_status(client, job_id, STATUS_TERMINAIS)
    esperados = {
        f"{item['variation_id']}.mp4"
        for item in job["variations"]
        if item["status"] == "completed"
    }

    resposta = await client.get(f"/api/v1/jobs/{job_id}/download")

    assert resposta.status_code == 200, resposta.text
    with zipfile.ZipFile(io.BytesIO(resposta.content)) as arquivo:
        assert set(arquivo.namelist()) == esperados
        assert arquivo.testzip() is None


async def test_download_devolve_404_quando_variacao_nao_existe(
    client: httpx.AsyncClient, video_valido: Path
) -> None:
    criacao = await _criar_job(client, video_valido, num_variations=2)
    job_id = criacao.json()["job_id"]
    await _esperar_status(client, job_id, STATUS_TERMINAIS)

    resposta = await client.get(
        f"/api/v1/jobs/{job_id}/variations/var-inexistente-999/download"
    )

    assert resposta.status_code == 404, resposta.text


# --- Cancelamento --------------------------------------------------------


async def test_job_vira_cancelled_quando_delete_chega_em_andamento(
    client: httpx.AsyncClient, video_longo: Path
) -> None:
    """Nenhuma variação pode continuar pending/running depois do cancelamento."""
    criacao = await _criar_job(client, video_longo, num_variations=6)
    job_id = criacao.json()["job_id"]

    delete = await client.delete(f"/api/v1/jobs/{job_id}")
    assert delete.status_code == 204, delete.text

    job = await _esperar_status(client, job_id, STATUS_TERMINAIS)
    assert job["status"] == "cancelled", job
    pendentes = [
        item["status"]
        for item in job["variations"]
        if item["status"] in {"pending", "running"}
    ]
    assert pendentes == []


async def test_status_continua_completed_quando_delete_chega_depois_do_fim(
    client: httpx.AsyncClient, video_valido: Path
) -> None:
    criacao = await _criar_job(client, video_valido, num_variations=2)
    job_id = criacao.json()["job_id"]
    concluido = await _esperar_status(client, job_id, STATUS_TERMINAIS)
    assert concluido["status"] == "completed", concluido

    delete = await client.delete(f"/api/v1/jobs/{job_id}")
    assert delete.status_code == 204, delete.text

    depois = await client.get(f"/api/v1/jobs/{job_id}")
    assert depois.status_code == 200
    assert depois.json()["status"] == "completed"


# --- Validação de entrada ------------------------------------------------


async def test_responde_400_quando_arquivo_nao_e_video(
    client: httpx.AsyncClient
) -> None:
    resposta = await client.post(
        "/api/v1/jobs",
        files={"file": ("nota.txt", b"isto nao e um video" * 100, "video/mp4")},
        data={"num_variations": "2"},
    )

    assert resposta.status_code == 400, resposta.text
    assert resposta.headers["content-type"].startswith("application/problem+json")


async def test_responde_400_quando_num_variations_passa_do_maximo(
    client: httpx.AsyncClient, video_valido: Path
) -> None:
    resposta = await _criar_job(client, video_valido, num_variations=7)

    assert resposta.status_code == 400, resposta.text
    assert resposta.headers["content-type"].startswith("application/problem+json")


# --- Health --------------------------------------------------------------


async def test_health_responde_ok_sem_expor_versao_do_ffmpeg(
    client: httpx.AsyncClient
) -> None:
    """Contrato: status "ok" e a disponibilidade do FFmpeg, sem a versão.

    Número de versão é insumo de reconhecimento para quem procura exploit
    conhecido, então a rota pública nunca pode devolvê-lo.
    """
    resposta = await client.get("/api/v1/health")

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo == {"status": "ok", "ffmpeg_version": "disponível"}

    versao_bruta = subprocess.run(
        ["ffmpeg", "-version"], check=True, capture_output=True, text=True
    ).stdout.split()[2]
    serializado = json.dumps(corpo, ensure_ascii=False)
    assert versao_bruta not in serializado
    assert re.search(r"\d+\.\d+", serializado) is None, serializado
