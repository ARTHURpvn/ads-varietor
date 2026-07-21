"""Testes de integração dos limites operacionais da API.

Cobre quota de disco, teto de resolução/duração da entrada, limites do
download em lote e a rotina de limpeza por retenção. Cada teste monta a app
com o seu próprio conjunto de variáveis de ambiente, porque os limites são
lidos do `Settings` cacheado no import do lifespan.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import secrets
import sqlite3
import subprocess
import zipfile
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest

from ads_varietor.api.main import create_app
from ads_varietor.core.generator import VariationGenerator
from ads_varietor.settings import get_settings

POLL_INTERVAL_SECONDS = 0.25
POLL_TIMEOUT_SECONDS = 60.0
STATUS_TERMINAIS = frozenset({"completed", "failed", "cancelled", "expired"})

# O vídeo de fixture é 160x120 (19200 pixels de área) e dura ~1s.
AREA_DO_VIDEO_FIXTURE = 160 * 120


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
    diretorio = tmp_path_factory.mktemp("fixtures-limites")
    return _gerar_video(diretorio / "entrada.mp4")


@pytest.fixture
def api_key() -> str:
    return secrets.token_urlsafe(32)


class Ambiente:
    """Handles do ambiente montado: cliente HTTP e caminhos do storage."""

    def __init__(self, client: httpx.AsyncClient, storage_dir: Path) -> None:
        self.client = client
        self.storage_dir = storage_dir

    @property
    def uploads_dir(self) -> Path:
        return self.storage_dir / "uploads"

    @property
    def jobs_dir(self) -> Path:
        return self.storage_dir / "jobs"

    @property
    def database_path(self) -> Path:
        return self.storage_dir / "jobs.sqlite3"


@pytest.fixture
def montar_app(
    tmp_path: Path, api_key: str, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Any]:
    """Devolve um context manager que sobe a app com limites customizados."""
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir()

    @asynccontextmanager
    async def _montar(**limites: str) -> AsyncIterator[Ambiente]:
        base = {
            "STORAGE_DIR": str(storage_dir),
            "API_KEYS": api_key,
            "MAX_CONCURRENT_FFMPEG": "2",
            "RATE_LIMIT_JOBS_PER_HOUR": "500",
            "RATE_LIMIT_REQUESTS_PER_MINUTE": "5000",
            "MAX_VARIATIONS_PER_JOB": "6",
            "CORS_ORIGINS": "",
        }
        base.update(limites)
        for nome, valor in base.items():
            monkeypatch.setenv(nome, valor)

        get_settings.cache_clear()
        app = create_app()
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
                headers={"X-API-Key": api_key},
                timeout=30.0,
            ) as http_client:
                yield Ambiente(http_client, storage_dir)

    try:
        yield _montar
    finally:
        get_settings.cache_clear()


# --- Helpers -------------------------------------------------------------


async def _criar_job(
    client: httpx.AsyncClient, video: Path, *, num_variations: int = 2
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


def _marcar_variacao_como_falha(
    database_path: Path, job_id: str, variation_id: str
) -> None:
    """Força uma variação para 'failed' sem apagar o arquivo que ela gerou.

    Assim o teste distingue "o ZIP usa a lista de variações concluídas" de
    "o ZIP varre o diretório": o arquivo da variação falha continua no disco.
    """
    connection = sqlite3.connect(database_path, timeout=10.0)
    try:
        connection.execute(
            """
            UPDATE variations
               SET status = 'failed', error = 'forçado pelo teste'
             WHERE job_id = ? AND variation_id = ?
            """,
            (job_id, variation_id),
        )
        connection.commit()
    finally:
        connection.close()


def _inserir_job_sintetico(
    database_path: Path,
    *,
    job_id: str,
    api_key: str,
    status: str,
    input_path: Path,
    output_dir: Path,
    idade_horas: float,
) -> None:
    """Insere direto no banco um job com `updated_at` no passado.

    Envelhecer o registro é a única forma de exercitar a retenção sem
    esperar horas de relógio.
    """
    momento = (
        datetime.now(timezone.utc) - timedelta(hours=idade_horas)
    ).isoformat()
    api_key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()

    connection = sqlite3.connect(database_path, timeout=10.0)
    try:
        connection.execute(
            """
            INSERT INTO jobs (
                job_id, api_key_hash, status, num_variations,
                input_path, output_dir, created_at, updated_at
            ) VALUES (?, ?, ?, 1, ?, ?, ?, ?)
            """,
            (
                job_id,
                api_key_hash,
                status,
                str(input_path),
                str(output_dir),
                momento,
                momento,
            ),
        )
        params = VariationGenerator().generate(1)[0].model_dump(mode="json")
        connection.execute(
            """
            INSERT INTO variations (job_id, variation_id, status, params_json)
            VALUES (?, 'var-001', 'completed', ?)
            """,
            (job_id, json.dumps(params)),
        )
        connection.commit()
    finally:
        connection.close()


def _preparar_arquivos_do_job(
    ambiente: Ambiente, job_id: str
) -> tuple[Path, Path]:
    """Cria no storage o upload e a saída de um job sintético."""
    ambiente.uploads_dir.mkdir(parents=True, exist_ok=True)
    input_path = ambiente.uploads_dir / f"{job_id}.mp4"
    input_path.write_bytes(b"conteudo de entrada")

    output_dir = ambiente.jobs_dir / job_id
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "var-001.mp4").write_bytes(b"conteudo de saida")
    return input_path, output_dir


async def _esperar_condicao(
    condicao: Any, *, descricao: str, timeout: float = 20.0
) -> None:
    limite = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < limite:
        if condicao():
            return
        await asyncio.sleep(0.2)
    raise AssertionError(f"Condição não satisfeita em {timeout}s: {descricao}")


async def _esperar_condicao_async(
    condicao: Any, *, descricao: str, timeout: float = 20.0
) -> None:
    limite = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < limite:
        if await condicao():
            return
        await asyncio.sleep(0.2)
    raise AssertionError(f"Condição não satisfeita em {timeout}s: {descricao}")


# --- (d) Quota de disco considerando a saída -----------------------------


async def test_responde_507_quando_reserva_da_saida_nao_cabe_na_quota(
    montar_app: Any, video_valido: Path
) -> None:
    """A reserva é max_upload_bytes * (1 + num_variations), não só o upload.

    Com 1 MB por upload e 2 variações, a reserva é de 3 MB; a quota de 2 MB
    não comporta o job mesmo com o vídeo enviado ocupando poucos KB.
    """
    async with montar_app(
        MAX_UPLOAD_BYTES=str(1024 * 1024),
        MAX_STORAGE_BYTES=str(2 * 1024 * 1024),
    ) as ambiente:
        resposta = await _criar_job(ambiente.client, video_valido, num_variations=2)

        assert resposta.status_code == 507, resposta.text
        assert not list(ambiente.uploads_dir.iterdir())


async def test_responde_202_quando_a_quota_comporta_a_reserva_da_saida(
    montar_app: Any, video_valido: Path
) -> None:
    """Mesmo POST do teste anterior, mudando só a quota: precisa passar."""
    async with montar_app(
        MAX_UPLOAD_BYTES=str(1024 * 1024),
        MAX_STORAGE_BYTES=str(100 * 1024 * 1024),
    ) as ambiente:
        resposta = await _criar_job(ambiente.client, video_valido, num_variations=2)

        assert resposta.status_code == 202, resposta.text
        assert resposta.json()["status"] == "pending"


async def test_507_sai_em_problem_json_sem_vazar_caminho_quando_falta_espaco(
    montar_app: Any, video_valido: Path
) -> None:
    async with montar_app(
        MAX_UPLOAD_BYTES=str(1024 * 1024),
        MAX_STORAGE_BYTES=str(2 * 1024 * 1024),
    ) as ambiente:
        resposta = await _criar_job(ambiente.client, video_valido, num_variations=2)

        assert resposta.status_code == 507, resposta.text
        assert resposta.headers["content-type"].startswith(
            "application/problem+json"
        )
        corpo = resposta.json()
        assert corpo["status"] == 507
        assert corpo["title"] and corpo["detail"]
        assert set(corpo) >= {"type", "title", "status", "detail"}

        texto = resposta.text
        assert str(ambiente.storage_dir) not in texto
        assert str(ambiente.uploads_dir) not in texto
        assert "/" not in corpo["detail"]


# --- (f) Teto de resolução e duração da entrada --------------------------


async def test_responde_400_e_apaga_upload_quando_area_passa_do_maximo(
    montar_app: Any, video_valido: Path
) -> None:
    """Área acima de MAX_INPUT_PIXELS é rejeitada e não deixa lixo em uploads."""
    async with montar_app(
        MAX_INPUT_PIXELS=str(AREA_DO_VIDEO_FIXTURE - 1),
    ) as ambiente:
        resposta = await _criar_job(ambiente.client, video_valido, num_variations=2)

        assert resposta.status_code == 400, resposta.text
        assert resposta.headers["content-type"].startswith(
            "application/problem+json"
        )
        assert list(ambiente.uploads_dir.iterdir()) == []


async def test_responde_400_quando_duracao_passa_do_maximo(
    montar_app: Any, video_valido: Path
) -> None:
    async with montar_app(
        MAX_INPUT_DURATION_SECONDS="0.5",
    ) as ambiente:
        resposta = await _criar_job(ambiente.client, video_valido, num_variations=2)

        assert resposta.status_code == 400, resposta.text
        assert list(ambiente.uploads_dir.iterdir()) == []


async def test_responde_202_quando_video_esta_exatamente_dentro_dos_limites(
    montar_app: Any, video_valido: Path
) -> None:
    """A comparação é estritamente `>`: a área exata do vídeo deve passar."""
    async with montar_app(
        MAX_INPUT_PIXELS=str(AREA_DO_VIDEO_FIXTURE),
        MAX_INPUT_DURATION_SECONDS="5",
    ) as ambiente:
        resposta = await _criar_job(ambiente.client, video_valido, num_variations=2)

        assert resposta.status_code == 202, resposta.text


# --- (a) Download em lote (ZIP) ------------------------------------------


async def test_download_em_lote_devolve_413_quando_zip_passa_do_maximo(
    montar_app: Any, video_valido: Path
) -> None:
    async with montar_app(MAX_ZIP_BYTES="1") as ambiente:
        criacao = await _criar_job(ambiente.client, video_valido, num_variations=2)
        job_id = criacao.json()["job_id"]
        job = await _esperar_status(ambiente.client, job_id, STATUS_TERMINAIS)
        assert job["status"] == "completed", job

        resposta = await ambiente.client.get(f"/api/v1/jobs/{job_id}/download")

        assert resposta.status_code == 413, resposta.text
        assert resposta.headers["content-type"].startswith(
            "application/problem+json"
        )


async def test_zip_traz_so_as_concluidas_quando_uma_variacao_falhou(
    montar_app: Any, video_valido: Path
) -> None:
    """O ZIP monta a partir da lista de variações, não do conteúdo do diretório.

    A variação marcada como falha continua com o arquivo no disco: se o ZIP
    fosse montado varrendo o diretório, ela apareceria no pacote.
    """
    async with montar_app() as ambiente:
        criacao = await _criar_job(ambiente.client, video_valido, num_variations=2)
        job_id = criacao.json()["job_id"]
        job = await _esperar_status(ambiente.client, job_id, STATUS_TERMINAIS)
        assert [item["status"] for item in job["variations"]] == ["completed"] * 2

        falha, mantida = (item["variation_id"] for item in job["variations"])
        _marcar_variacao_como_falha(ambiente.database_path, job_id, falha)
        arquivo_da_falha = ambiente.jobs_dir / job_id / f"{falha}.mp4"
        assert arquivo_da_falha.is_file()

        resposta = await ambiente.client.get(f"/api/v1/jobs/{job_id}/download")

        assert resposta.status_code == 200, resposta.text
        with zipfile.ZipFile(io.BytesIO(resposta.content)) as pacote:
            assert pacote.namelist() == [f"{mantida}.mp4"]
            assert pacote.testzip() is None


async def test_nao_sobra_zip_no_diretorio_do_job_apos_o_download(
    montar_app: Any, video_valido: Path
) -> None:
    async with montar_app() as ambiente:
        criacao = await _criar_job(ambiente.client, video_valido, num_variations=2)
        job_id = criacao.json()["job_id"]
        await _esperar_status(ambiente.client, job_id, STATUS_TERMINAIS)

        resposta = await ambiente.client.get(f"/api/v1/jobs/{job_id}/download")
        assert resposta.status_code == 200, resposta.text

        diretorio = ambiente.jobs_dir / job_id
        assert list(diretorio.glob("*.zip")) == []


# --- (h) Limpeza por retenção --------------------------------------------


async def test_job_concluido_e_antigo_vira_expired_e_perde_arquivos(
    montar_app: Any
) -> None:
    async with montar_app(
        RETENTION_HOURS="1", CLEANUP_INTERVAL_SECONDS="1"
    ) as ambiente:
        job_id = "jobconcluidoantigo"
        entrada, saida = _preparar_arquivos_do_job(ambiente, job_id)
        _inserir_job_sintetico(
            ambiente.database_path,
            job_id=job_id,
            api_key=ambiente.client.headers["X-API-Key"],
            status="completed",
            input_path=entrada,
            output_dir=saida,
            idade_horas=3,
        )

        # A limpeza remove a saída, remove a entrada e só então marca o job
        # como expirado; esperar pelo status evita ler um estado parcial.
        async def _expirou() -> bool:
            resposta = await ambiente.client.get(f"/api/v1/jobs/{job_id}")
            assert resposta.status_code == 200, resposta.text
            return bool(resposta.json()["status"] == "expired")

        await _esperar_condicao_async(
            _expirou, descricao=f"job {job_id} marcado como expired"
        )

        assert not saida.exists()
        assert not entrada.exists()


async def test_job_em_execucao_nao_e_tocado_pela_limpeza_mesmo_antigo(
    montar_app: Any
) -> None:
    """Um job ainda rodando não pode perder os arquivos debaixo do FFmpeg.

    O job concluído serve de canário: quando ele expira, a limpeza
    comprovadamente rodou naquele ciclo — sem ele o teste passaria mesmo se
    a rotina nunca tivesse executado.
    """
    async with montar_app(
        RETENTION_HOURS="1", CLEANUP_INTERVAL_SECONDS="1"
    ) as ambiente:
        api_key = ambiente.client.headers["X-API-Key"]

        rodando_id = "jobrodandoantigo"
        entrada_rodando, saida_rodando = _preparar_arquivos_do_job(
            ambiente, rodando_id
        )
        _inserir_job_sintetico(
            ambiente.database_path,
            job_id=rodando_id,
            api_key=api_key,
            status="running",
            input_path=entrada_rodando,
            output_dir=saida_rodando,
            idade_horas=5,
        )

        canario_id = "jobcanarioantigo"
        entrada_canario, saida_canario = _preparar_arquivos_do_job(
            ambiente, canario_id
        )
        _inserir_job_sintetico(
            ambiente.database_path,
            job_id=canario_id,
            api_key=api_key,
            status="completed",
            input_path=entrada_canario,
            output_dir=saida_canario,
            idade_horas=5,
        )

        await _esperar_condicao(
            lambda: not saida_canario.exists(),
            descricao="limpeza executou pelo menos um ciclo",
        )

        assert entrada_rodando.is_file()
        assert (saida_rodando / "var-001.mp4").is_file()
        resposta = await ambiente.client.get(f"/api/v1/jobs/{rodando_id}")
        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["status"] == "running"
