"""Testes da interface servida pela própria aplicação e do modo público.

O Caddy foi removido: a mesma aplicação passou a servir os arquivos do
frontend e a aceitar chamadas da interface sem API key quando `UI_PUBLIC`
está ligado.
"""

from __future__ import annotations

import secrets
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from ads_varietor.api.main import create_app
from ads_varietor.settings import get_settings

CHAVE = secrets.token_urlsafe(32)


def _preparar_build(diretorio: Path) -> Path:
    """Cria um build de frontend mínimo, como o Vite produziria."""
    dist = diretorio / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        "<!doctype html><title>interface</title>", encoding="utf-8"
    )
    (dist / "assets" / "index-abc123.js").write_text(
        "console.log('app')", encoding="utf-8"
    )
    (dist / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    return dist


async def _cliente(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    com_frontend: bool,
    ui_public: bool,
) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("API_KEYS", CHAVE)
    monkeypatch.setenv("UI_PUBLIC", "true" if ui_public else "false")
    monkeypatch.setenv("RECONCILE_ENABLED", "false")
    if com_frontend:
        monkeypatch.setenv("FRONTEND_DIR", str(_preparar_build(tmp_path)))
    else:
        monkeypatch.delenv("FRONTEND_DIR", raising=False)

    get_settings.cache_clear()
    app = create_app()

    async with app.router.lifespan_context(app):
        transporte = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transporte, base_url="http://teste"
        ) as cliente:
            yield cliente

    get_settings.cache_clear()


@pytest.fixture
async def cliente_com_interface(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> AsyncIterator[httpx.AsyncClient]:
    async for cliente in _cliente(
        monkeypatch, tmp_path, com_frontend=True, ui_public=True
    ):
        yield cliente


@pytest.fixture
async def cliente_fechado(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> AsyncIterator[httpx.AsyncClient]:
    async for cliente in _cliente(
        monkeypatch, tmp_path, com_frontend=True, ui_public=False
    ):
        yield cliente


# ---------------------------------------------------------------------------
# Interface servida pela aplicação
# ---------------------------------------------------------------------------


async def test_raiz_devolve_o_index_quando_ha_build(
    cliente_com_interface: httpx.AsyncClient,
) -> None:
    resposta = await cliente_com_interface.get("/")

    assert resposta.status_code == 200
    assert "text/html" in resposta.headers["content-type"]
    assert "interface" in resposta.text


async def test_rota_desconhecida_cai_no_index_quando_e_navegacao_da_spa(
    cliente_com_interface: httpx.AsyncClient,
) -> None:
    resposta = await cliente_com_interface.get("/qualquer/rota/da/spa")

    assert resposta.status_code == 200
    assert "interface" in resposta.text


async def test_rota_de_api_inexistente_devolve_404_e_nao_html(
    cliente_com_interface: httpx.AsyncClient,
) -> None:
    """Sem esta guarda, um erro de API viria como HTML com status 200."""
    resposta = await cliente_com_interface.get("/api/v1/rota-que-nao-existe")

    assert resposta.status_code == 404
    assert "<title>" not in resposta.text


async def test_asset_vem_com_cache_longo_quando_tem_hash_no_nome(
    cliente_com_interface: httpx.AsyncClient,
) -> None:
    resposta = await cliente_com_interface.get("/assets/index-abc123.js")

    assert resposta.status_code == 200
    assert "immutable" in resposta.headers["cache-control"]


async def test_index_nao_e_cacheado_para_nao_servir_versao_velha(
    cliente_com_interface: httpx.AsyncClient,
) -> None:
    resposta = await cliente_com_interface.get("/")

    assert resposta.headers["cache-control"] == "no-cache"


async def test_arquivo_solto_da_raiz_e_servido_quando_existe(
    cliente_com_interface: httpx.AsyncClient,
) -> None:
    resposta = await cliente_com_interface.get("/favicon.svg")

    assert resposta.status_code == 200
    assert "<svg/>" in resposta.text


async def test_cabecalhos_de_seguranca_acompanham_a_resposta(
    cliente_com_interface: httpx.AsyncClient,
) -> None:
    resposta = await cliente_com_interface.get("/")

    assert resposta.headers["x-content-type-options"] == "nosniff"
    assert resposta.headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in resposta.headers["content-security-policy"]


async def test_traversal_no_caminho_da_interface_nao_le_arquivo_de_fora(
    cliente_com_interface: httpx.AsyncClient,
) -> None:
    for payload in ["../../../../etc/passwd", "..%2f..%2fetc%2fpasswd"]:
        resposta = await cliente_com_interface.get(f"/{payload}")

        assert resposta.status_code in {200, 400, 404}
        assert "root:" not in resposta.text


# ---------------------------------------------------------------------------
# Modo público
# ---------------------------------------------------------------------------


async def test_api_aceita_chamada_sem_chave_quando_ui_publica(
    cliente_com_interface: httpx.AsyncClient,
) -> None:
    resposta = await cliente_com_interface.get("/api/v1/usage")

    assert resposta.status_code == 200


async def test_api_recusa_chamada_sem_chave_quando_ui_nao_e_publica(
    cliente_fechado: httpx.AsyncClient,
) -> None:
    resposta = await cliente_fechado.get("/api/v1/usage")

    assert resposta.status_code == 401


async def test_chave_invalida_continua_recusada_mesmo_com_ui_publica(
    cliente_com_interface: httpx.AsyncClient,
) -> None:
    """Mandar chave errada é erro, e não vira acesso público por acidente."""
    resposta = await cliente_com_interface.get(
        "/api/v1/usage", headers={"X-API-Key": "chave-errada-mas-longa-o-bastante"}
    )

    assert resposta.status_code == 401


async def test_chave_valida_continua_funcionando_com_ui_publica(
    cliente_com_interface: httpx.AsyncClient,
) -> None:
    resposta = await cliente_com_interface.get(
        "/api/v1/usage", headers={"X-API-Key": CHAVE}
    )

    assert resposta.status_code == 200


async def test_dono_publico_e_separado_do_dono_da_chave(
    cliente_com_interface: httpx.AsyncClient, tmp_path: Path
) -> None:
    """Job criado pela interface pública não pertence à chave, e vice-versa.

    Sem isso, o consumo da interface entraria na quota de quem usa a API
    programaticamente.
    """
    video = tmp_path / "entrada.mp4"
    import subprocess

    from ads_varietor.core.probe import find_binary

    subprocess.run(
        [
            find_binary("ffmpeg"), "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=s=160x120:d=1",
            "-c:v", "libx264", "-preset", "ultrafast", "-y", str(video),
        ],
        check=True,
    )

    with video.open("rb") as arquivo:
        criado = await cliente_com_interface.post(
            "/api/v1/jobs",
            files={"file": ("v.mp4", arquivo, "video/mp4")},
            data={"num_variations": "1", "mode": "metadata_only"},
        )
    assert criado.status_code == 202
    job_id = criado.json()["job_id"]

    # A interface (sem chave) enxerga o próprio job.
    assert (await cliente_com_interface.get(f"/api/v1/jobs/{job_id}")).status_code == 200

    # Quem usa a chave não enxerga o job da interface.
    com_chave = await cliente_com_interface.get(
        f"/api/v1/jobs/{job_id}", headers={"X-API-Key": CHAVE}
    )
    assert com_chave.status_code == 404
