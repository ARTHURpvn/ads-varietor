"""Testes de integração da quota por chave, do endpoint de uso e da
purga opcional depois do download em lote.

Cada teste monta a app com o seu próprio conjunto de variáveis de ambiente,
porque os limites são lidos do `Settings` cacheado no import do lifespan.
"""

from __future__ import annotations

import asyncio
import json
import secrets
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
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
    import subprocess

    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
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
    diretorio = tmp_path_factory.mktemp("fixtures-uso")
    return _gerar_video(diretorio / "entrada.mp4")


@pytest.fixture
def api_key() -> str:
    return secrets.token_urlsafe(32)


@pytest.fixture
def api_key_secundaria() -> str:
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
    client: httpx.AsyncClient,
    video: Path,
    *,
    num_variations: int = 2,
    api_key: str | None = None,
) -> httpx.Response:
    headers = {"X-API-Key": api_key} if api_key else None
    return await client.post(
        "/api/v1/jobs",
        files={"file": (video.name, video.read_bytes(), "video/mp4")},
        data={"num_variations": str(num_variations)},
        headers=headers,
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


# --- Quota por chave -----------------------------------------------------


async def test_quota_por_chave_recusa_com_507_e_titulo_proprio(
    montar_app: Any, video_valido: Path
) -> None:
    """A quota individual barra a chave sem depender da quota global.

    O espaço global é folgado de propósito: quem recusa aqui é o limite da
    chave, e a mensagem precisa deixar isso claro para o usuário.
    """
    async with montar_app(
        MAX_STORAGE_BYTES=str(10 * 1024 * 1024 * 1024),
        MAX_STORAGE_BYTES_PER_KEY="1024",
    ) as ambiente:
        resposta = await _criar_job(ambiente.client, video_valido)

        assert resposta.status_code == 507, resposta.text
        corpo = resposta.json()
        assert "limite" in corpo["title"].lower()
        assert corpo["title"] != "Sem espaço disponível"
        # A cota é formatada na unidade certa: exibir "0.0 GB" para uma cota
        # pequena não diria nada ao usuário.
        assert "1.0 KB" in corpo["detail"]


async def test_507_de_servico_lotado_tem_titulo_diferente_do_507_da_chave(
    montar_app: Any, video_valido: Path
) -> None:
    """As duas causas de 507 precisam ser distinguíveis pelo cliente."""
    async with montar_app(
        MAX_UPLOAD_BYTES=str(1024 * 1024),
        MAX_STORAGE_BYTES=str(2 * 1024 * 1024),
    ) as ambiente:
        resposta = await _criar_job(ambiente.client, video_valido)

        assert resposta.status_code == 507, resposta.text
        assert resposta.json()["title"] == "Sem espaço disponível"


async def test_quota_por_chave_nao_vaza_numeros_globais_nem_de_outra_chave(
    montar_app: Any, video_valido: Path
) -> None:
    quota_global = 10 * 1024 * 1024 * 1024
    async with montar_app(
        MAX_STORAGE_BYTES=str(quota_global),
        MAX_STORAGE_BYTES_PER_KEY="1024",
    ) as ambiente:
        resposta = await _criar_job(ambiente.client, video_valido)

        assert resposta.status_code == 507, resposta.text
        assert resposta.headers["content-type"].startswith(
            "application/problem+json"
        )
        texto = resposta.text
        assert str(quota_global) not in texto
        assert str(ambiente.storage_dir) not in texto
        assert "/" not in resposta.json()["detail"]


async def test_upload_e_apagado_quando_a_quota_da_chave_recusa_o_job(
    montar_app: Any, video_valido: Path
) -> None:
    async with montar_app(
        MAX_STORAGE_BYTES=str(10 * 1024 * 1024 * 1024),
        MAX_STORAGE_BYTES_PER_KEY="1024",
    ) as ambiente:
        resposta = await _criar_job(ambiente.client, video_valido)

        assert resposta.status_code == 507, resposta.text
        assert list(ambiente.uploads_dir.iterdir()) == []


async def test_quota_por_chave_folgada_aceita_o_mesmo_job(
    montar_app: Any, video_valido: Path
) -> None:
    """Mesmo POST do teste anterior, mudando só a quota da chave."""
    async with montar_app(
        MAX_STORAGE_BYTES=str(10 * 1024 * 1024 * 1024),
        MAX_STORAGE_BYTES_PER_KEY=str(1024 * 1024 * 1024),
    ) as ambiente:
        resposta = await _criar_job(ambiente.client, video_valido)

        assert resposta.status_code == 202, resposta.text


async def test_consumo_de_uma_chave_nao_bloqueia_a_outra(
    montar_app: Any,
    video_valido: Path,
    api_key: str,
    api_key_secundaria: str,
) -> None:
    """O motivo de existir a quota por chave: isolamento entre clientes.

    A quota individual é medida por chave, então a segunda chave começa do
    zero mesmo depois de a primeira ter gravado jobs.
    """
    async with montar_app(
        API_KEYS=f"{api_key},{api_key_secundaria}",
        MAX_STORAGE_BYTES=str(10 * 1024 * 1024 * 1024),
        MAX_STORAGE_BYTES_PER_KEY=str(64 * 1024 * 1024),
    ) as ambiente:
        primeira = await _criar_job(ambiente.client, video_valido)
        assert primeira.status_code == 202, primeira.text
        await _esperar_status(
            ambiente.client, primeira.json()["job_id"], STATUS_TERMINAIS
        )

        segunda = await _criar_job(
            ambiente.client, video_valido, api_key=api_key_secundaria
        )

        assert segunda.status_code == 202, segunda.text

        uso = await ambiente.client.get(
            "/api/v1/usage", headers={"X-API-Key": api_key_secundaria}
        )
        assert uso.status_code == 200, uso.text
        assert uso.json()["your_usage"]["jobs"] == 1


# --- Endpoint de uso -----------------------------------------------------


async def test_usage_exige_autenticacao(montar_app: Any) -> None:
    async with montar_app() as ambiente:
        resposta = await ambiente.client.get(
            "/api/v1/usage",
            headers={"X-API-Key": "chave-errada-mas-com-24-caracteres"},
        )

        assert resposta.status_code == 401, resposta.text


async def test_usage_devolve_quota_disponivel_e_percentual_coerentes(
    montar_app: Any
) -> None:
    quota = 100 * 1024 * 1024
    async with montar_app(MAX_STORAGE_BYTES=str(quota)) as ambiente:
        resposta = await ambiente.client.get("/api/v1/usage")

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["quota_bytes"] == quota
        assert corpo["used_bytes"] + corpo["available_bytes"] <= quota + 1
        assert 0.0 <= corpo["usage_percent"] <= 100.0
        assert corpo["warn_percent"] == 80
        assert corpo["over_threshold"] is False
        assert corpo["retention_hours"] > 0


async def test_usage_contabiliza_o_job_da_chave_que_perguntou(
    montar_app: Any, video_valido: Path
) -> None:
    async with montar_app() as ambiente:
        criacao = await _criar_job(ambiente.client, video_valido)
        job_id = criacao.json()["job_id"]
        await _esperar_status(ambiente.client, job_id, STATUS_TERMINAIS)

        resposta = await ambiente.client.get("/api/v1/usage")

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["jobs_by_status"]["completed"] == 1
        assert corpo["your_usage"]["jobs"] == 1
        assert corpo["your_usage"]["jobs_by_status"]["completed"] == 1
        assert corpo["your_usage"]["used_bytes"] > 0
        assert corpo["your_usage"]["available_bytes"] >= 0


async def test_usage_marca_over_threshold_quando_limiar_e_baixo(
    montar_app: Any, video_valido: Path
) -> None:
    # A quota precisa ser pequena para o vídeo de fixture representar mais
    # de 1% dela; com a quota padrão de 20 GB nenhum teste chegaria perto.
    async with montar_app(
        STORAGE_WARN_PERCENT="1",
        MAX_UPLOAD_BYTES="100000",
        MAX_STORAGE_BYTES=str(1024 * 1024),
    ) as ambiente:
        criacao = await _criar_job(ambiente.client, video_valido)
        await _esperar_status(
            ambiente.client, criacao.json()["job_id"], STATUS_TERMINAIS
        )

        corpo = (await ambiente.client.get("/api/v1/usage")).json()

        assert corpo["warn_percent"] == 1
        assert corpo["over_threshold"] is True


async def test_usage_nao_e_cacheavel(montar_app: Any) -> None:
    async with montar_app() as ambiente:
        resposta = await ambiente.client.get("/api/v1/usage")

        assert resposta.headers["cache-control"] == "no-store"


async def test_usage_nao_expoe_caminho_de_disco(montar_app: Any) -> None:
    async with montar_app() as ambiente:
        resposta = await ambiente.client.get("/api/v1/usage")

        assert str(ambiente.storage_dir) not in resposta.text


# --- Purga depois do download em lote ------------------------------------


async def test_download_em_lote_apaga_os_arquivos_quando_a_opcao_esta_ligada(
    montar_app: Any, video_valido: Path
) -> None:
    async with montar_app(DELETE_AFTER_BATCH_DOWNLOAD="true") as ambiente:
        criacao = await _criar_job(ambiente.client, video_valido)
        job_id = criacao.json()["job_id"]
        await _esperar_status(ambiente.client, job_id, STATUS_TERMINAIS)

        resposta = await ambiente.client.get(f"/api/v1/jobs/{job_id}/download")
        assert resposta.status_code == 200, resposta.text
        assert len(resposta.content) > 0

        assert not (ambiente.jobs_dir / job_id).exists()
        detalhe = await ambiente.client.get(f"/api/v1/jobs/{job_id}")
        assert detalhe.json()["status"] == "expired"


async def test_download_em_lote_preserva_os_arquivos_por_padrao(
    montar_app: Any, video_valido: Path
) -> None:
    """O default é desligado: rebaixar o mesmo job precisa continuar valendo."""
    async with montar_app() as ambiente:
        criacao = await _criar_job(ambiente.client, video_valido)
        job_id = criacao.json()["job_id"]
        await _esperar_status(ambiente.client, job_id, STATUS_TERMINAIS)

        primeira = await ambiente.client.get(f"/api/v1/jobs/{job_id}/download")
        assert primeira.status_code == 200, primeira.text

        assert (ambiente.jobs_dir / job_id).is_dir()
        segunda = await ambiente.client.get(f"/api/v1/jobs/{job_id}/download")
        assert segunda.status_code == 200, segunda.text


# --- Cancelamento libera o arquivo de entrada ----------------------------


async def test_cancelar_job_pendente_apaga_o_upload(
    montar_app: Any, video_valido: Path
) -> None:
    """Cancelamento sem task viva também precisa liberar o disco."""
    async with montar_app() as ambiente:
        criacao = await _criar_job(ambiente.client, video_valido)
        job_id = criacao.json()["job_id"]

        resposta = await ambiente.client.delete(f"/api/v1/jobs/{job_id}")
        assert resposta.status_code == 204, resposta.text

        await _esperar_status(ambiente.client, job_id, STATUS_TERMINAIS)
        assert list(ambiente.uploads_dir.iterdir()) == []
