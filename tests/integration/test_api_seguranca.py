"""Testes de segurança da API: autenticação, autorização, traversal,
limites de upload, rate limit, vazamento de informação e startup seguro.

A aplicação é montada de verdade (create_app + lifespan) e exercitada por
httpx.ASGITransport — nada do código sob teste é mockado.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any
from unittest import mock

import httpx
import pytest

from ads_varietor.api.main import create_app
from ads_varietor.settings import get_settings

CHAVE_A = "chave-de-teste-alpha-com-tamanho-suficiente-01"
CHAVE_B = "chave-de-teste-bravo-com-tamanho-suficiente-02"
CHAVE_INVALIDA = "chave-que-nao-esta-configurada-em-lugar-nenhum"

BASE_URL = "http://testserver"
PREFIXO = "/api/v1"

# Rotas que exigem X-API-Key. O job_id/variation_id é irrelevante: a
# autenticação roda antes de qualquer consulta ao banco.
ROTAS_PROTEGIDAS: tuple[tuple[str, str], ...] = (
    ("POST", f"{PREFIXO}/jobs"),
    ("GET", f"{PREFIXO}/jobs/abc123"),
    ("DELETE", f"{PREFIXO}/jobs/abc123"),
    ("GET", f"{PREFIXO}/jobs/abc123/download"),
    ("GET", f"{PREFIXO}/jobs/abc123/variations/var-1/download"),
)

# Marcadores que jamais podem aparecer numa resposta de erro.
MARCADORES_INTERNOS = ("Traceback", "Exception", ".py", "/Users/", "/private/")


def _base_env(tmp_path: Path) -> dict[str, str]:
    """Ambiente mínimo e isolado: storage sempre dentro do tmp_path."""
    return {
        "STORAGE_DIR": str(tmp_path / "storage"),
        "API_KEYS": f"{CHAVE_A},{CHAVE_B}",
        "CORS_ORIGINS": "",
        "MAX_UPLOAD_BYTES": str(10 * 1024 * 1024),
        "MAX_STORAGE_BYTES": str(2 * 1024 * 1024 * 1024),
        "MAX_VARIATIONS_PER_JOB": "5",
        "MAX_CONCURRENT_FFMPEG": "2",
        "FFMPEG_TIMEOUT_SECONDS": "60",
        # Alto por padrão: só os testes de rate limit baixam o teto.
        "RATE_LIMIT_JOBS_PER_HOUR": "100",
        "RATE_LIMIT_REQUESTS_PER_MINUTE": "500",
        # A limpeza periódica não deve rodar durante o teste.
        "CLEANUP_INTERVAL_SECONDS": "3600",
        "RETENTION_HOURS": "24",
    }


@contextlib.asynccontextmanager
async def api_client(
    tmp_path: Path, **overrides: str
) -> AsyncIterator[httpx.AsyncClient]:
    """Sobe a aplicação real (lifespan incluso) e devolve um client HTTP."""
    env = _base_env(tmp_path) | overrides
    with mock.patch.dict(os.environ, env, clear=False):
        get_settings.cache_clear()
        app = create_app()
        try:
            async with app.router.lifespan_context(app):
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(
                    transport=transport, base_url=BASE_URL
                ) as client:
                    yield client
        finally:
            get_settings.cache_clear()


async def _iniciar_app(tmp_path: Path, **overrides: str) -> None:
    """Executa apenas o startup da aplicação; propaga a recusa, se houver."""
    env = _base_env(tmp_path) | overrides
    with mock.patch.dict(os.environ, env, clear=False):
        get_settings.cache_clear()
        app = create_app()
        try:
            async with app.router.lifespan_context(app):
                pass
        finally:
            get_settings.cache_clear()


@pytest.fixture(scope="module")
def video_pequeno(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Vídeo real de 1s e 160x120, barato de renderizar."""
    destino = tmp_path_factory.mktemp("fixtures") / "entrada.mp4"
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=s=160x120:r=10:d=1",
            "-f", "lavfi", "-i", "sine=f=440:d=1",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", "-y", str(destino),
        ],
        check=True,
        capture_output=True,
    )
    return destino


@pytest.fixture
def uploads_multipart(video_pequeno: Path) -> Iterator[dict[str, Any]]:
    """Corpo multipart pronto para POST /jobs com uma única variação."""
    conteudo = video_pequeno.read_bytes()
    yield {
        "files": {"file": ("entrada.mp4", conteudo, "video/mp4")},
        "data": {"num_variations": "1"},
    }


def _corpo_problem(resposta: httpx.Response) -> dict[str, Any]:
    corpo = resposta.json()
    assert isinstance(corpo, dict)
    return corpo


async def _criar_job(
    client: httpx.AsyncClient, chave: str, multipart: dict[str, Any]
) -> str:
    resposta = await client.post(
        f"{PREFIXO}/jobs", headers={"X-API-Key": chave}, **multipart
    )
    assert resposta.status_code == 202, resposta.text
    return resposta.json()["job_id"]


# --------------------------------------------------------------------------
# Autenticação
# --------------------------------------------------------------------------


async def test_health_responde_sem_chave_quando_rota_e_publica(
    tmp_path: Path,
) -> None:
    """Sanidade: a app está de pé e só as rotas de job são protegidas."""
    async with api_client(tmp_path) as client:
        resposta = await client.get(f"{PREFIXO}/health")
    assert resposta.status_code == 200
    assert resposta.json()["status"] == "ok"


@pytest.mark.parametrize(("metodo", "caminho"), ROTAS_PROTEGIDAS)
async def test_retorna_401_quando_header_api_key_ausente(
    tmp_path: Path, metodo: str, caminho: str
) -> None:
    async with api_client(tmp_path) as client:
        resposta = await client.request(metodo, caminho)

    assert resposta.status_code == 401
    assert resposta.headers["content-type"].startswith(
        "application/problem+json"
    )


@pytest.mark.parametrize(("metodo", "caminho"), ROTAS_PROTEGIDAS)
async def test_retorna_401_quando_chave_invalida(
    tmp_path: Path, metodo: str, caminho: str
) -> None:
    async with api_client(tmp_path) as client:
        resposta = await client.request(
            metodo, caminho, headers={"X-API-Key": CHAVE_INVALIDA}
        )

    assert resposta.status_code == 401


async def test_retorna_401_quando_chave_e_prefixo_de_chave_valida(
    tmp_path: Path,
) -> None:
    """Comparação é do valor inteiro, não de prefixo."""
    async with api_client(tmp_path) as client:
        resposta = await client.get(
            f"{PREFIXO}/jobs/abc123", headers={"X-API-Key": CHAVE_A[:-1]}
        )

    assert resposta.status_code == 401


# --------------------------------------------------------------------------
# Autorização entre donos
# --------------------------------------------------------------------------


async def test_retorna_404_para_outra_chave_quando_job_pertence_a_chave_a(
    tmp_path: Path, uploads_multipart: dict[str, Any]
) -> None:
    """Job de outro dono some (404), nunca 403 — 403 confirmaria existência."""
    async with api_client(tmp_path) as client:
        job_id = await _criar_job(client, CHAVE_A, uploads_multipart)

        dono = await client.get(
            f"{PREFIXO}/jobs/{job_id}", headers={"X-API-Key": CHAVE_A}
        )
        assert dono.status_code == 200, dono.text

        cabecalho_b = {"X-API-Key": CHAVE_B}
        alheias = {
            "get": await client.get(
                f"{PREFIXO}/jobs/{job_id}", headers=cabecalho_b
            ),
            "download_zip": await client.get(
                f"{PREFIXO}/jobs/{job_id}/download", headers=cabecalho_b
            ),
            "download_variacao": await client.get(
                f"{PREFIXO}/jobs/{job_id}/variations/"
                f"{dono.json()['variations'][0]['variation_id']}/download",
                headers=cabecalho_b,
            ),
            "delete": await client.delete(
                f"{PREFIXO}/jobs/{job_id}", headers=cabecalho_b
            ),
        }

        for nome, resposta in alheias.items():
            assert resposta.status_code == 404, f"{nome}: {resposta.text}"

        # O DELETE alheio não pode ter afetado o job do dono.
        ainda_do_dono = await client.get(
            f"{PREFIXO}/jobs/{job_id}", headers={"X-API-Key": CHAVE_A}
        )
        assert ainda_do_dono.status_code == 200
        assert ainda_do_dono.json()["status"] != "cancelled"


# --------------------------------------------------------------------------
# Path traversal
# --------------------------------------------------------------------------


# Metade destes é descartada já no roteamento; a outra metade chega ao
# handler e precisa ser recusada pela validação de identificador.
TRAVERSAIS = (
    "..",
    "../..",
    "%2e%2e",
    "....",
    "..%2F..%2Fetc%2Fpasswd",
    "%2e%2e%2f%2e%2e%2fetc%2fpasswd",
    "..%252f..%252fetc%252fpasswd",
    "....//....//etc/passwd",
    "%2Fetc%2Fpasswd",
    "..%5C..%5Cetc%5Cpasswd",
    "..\\..\\etc\\passwd",
    "..%00",
    "job..%00",
    "..;/",
)


CONTEUDO_DA_ISCA = "root:x:0:0:CONTEUDO-SECRETO-FORA-DO-STORAGE:/root:/bin/sh"

# Status que a aplicação de fato responde a estes payloads: 400 (identificador
# recusado pela validação), 404 (job inexistente) e 307 (normalização de barra
# final feita pelo roteador, antes de qualquer handler).
STATUS_ACEITOS_NO_TRAVERSAL = frozenset({307, 400, 404})


def _plantar_isca(tmp_path: Path) -> Path:
    """Grava o arquivo-isca exatamente onde `../../etc/passwd` cairia.

    O diretório de jobs é `<storage>/jobs`, então dois níveis acima dele é
    o próprio tmp_path. A isca vai para `<tmp_path>/etc/passwd`: é o
    arquivo que os payloads de traversal alcançariam se o job_id virasse
    caminho no filesystem.
    """
    jobs_dir = tmp_path / "storage" / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)

    isca = tmp_path / "etc" / "passwd"
    isca.parent.mkdir(parents=True, exist_ok=True)
    isca.write_text(CONTEUDO_DA_ISCA, encoding="utf-8")

    # A isca só vale se o caminho relativo do payload realmente chegar nela.
    alcancado = Path(os.path.normpath(jobs_dir / "../../etc/passwd"))
    assert alcancado == isca, f"{alcancado} != {isca}"
    return isca


@pytest.mark.parametrize("payload", TRAVERSAIS)
async def test_bloqueia_traversal_quando_job_id_tenta_escapar(
    tmp_path: Path, payload: str
) -> None:
    isca = _plantar_isca(tmp_path)

    async with api_client(tmp_path) as client:
        resposta = await client.get(
            f"{PREFIXO}/jobs/{payload}", headers={"X-API-Key": CHAVE_A}
        )

    assert resposta.status_code in STATUS_ACEITOS_NO_TRAVERSAL, (
        f"{payload}: {resposta.status_code} {resposta.text[:200]}"
    )
    if resposta.status_code == 307:
        # O redirecionamento não pode levar para fora do recurso de jobs.
        assert resposta.headers["location"].startswith(
            f"{BASE_URL}{PREFIXO}/jobs/"
        )

    assert "CONTEUDO-SECRETO" not in resposta.text
    assert "root:" not in resposta.text
    # A isca continua onde estava: nenhum payload a leu, moveu ou apagou.
    assert isca.read_text(encoding="utf-8") == CONTEUDO_DA_ISCA


async def test_bloqueia_traversal_quando_variation_id_tenta_escapar(
    tmp_path: Path, uploads_multipart: dict[str, Any]
) -> None:
    """Mesmo com job_id legítimo do dono, o variation_id não vira caminho."""
    async with api_client(tmp_path) as client:
        job_id = await _criar_job(client, CHAVE_A, uploads_multipart)
        respostas = {
            payload: await client.get(
                f"{PREFIXO}/jobs/{job_id}/variations/{payload}/download",
                headers={"X-API-Key": CHAVE_A},
            )
            for payload in TRAVERSAIS
        }

    for payload, resposta in respostas.items():
        assert resposta.status_code != 200, f"{payload}: {resposta.text[:200]}"
        assert resposta.status_code in {307, 400, 404, 405, 422}, payload
        assert "root:" not in resposta.text


# --------------------------------------------------------------------------
# Upload acima do limite
# --------------------------------------------------------------------------


async def test_retorna_413_e_nao_deixa_residuo_quando_upload_excede_limite(
    tmp_path: Path,
) -> None:
    async with api_client(tmp_path, MAX_UPLOAD_BYTES="4096") as client:
        resposta = await client.post(
            f"{PREFIXO}/jobs",
            headers={"X-API-Key": CHAVE_A},
            files={"file": ("grande.mp4", b"\0" * 200_000, "video/mp4")},
            data={"num_variations": "1"},
        )

    assert resposta.status_code == 413, resposta.text
    corpo = _corpo_problem(resposta)
    assert corpo["status"] == 413

    uploads = tmp_path / "storage" / "uploads"
    residuos = [item for item in uploads.iterdir() if item.is_file()]
    assert residuos == [], f"upload residual: {residuos}"


async def test_retorna_400_e_nao_deixa_residuo_quando_arquivo_nao_e_video(
    tmp_path: Path,
) -> None:
    async with api_client(tmp_path) as client:
        resposta = await client.post(
            f"{PREFIXO}/jobs",
            headers={"X-API-Key": CHAVE_A},
            files={"file": ("falso.mp4", b"nao sou um video" * 100, "video/mp4")},
            data={"num_variations": "1"},
        )

    assert resposta.status_code == 400, resposta.text
    uploads = tmp_path / "storage" / "uploads"
    assert [item for item in uploads.iterdir() if item.is_file()] == []


# --------------------------------------------------------------------------
# Rate limit
# --------------------------------------------------------------------------


async def test_retorna_429_com_retry_after_quando_limite_de_jobs_estourado(
    tmp_path: Path, uploads_multipart: dict[str, Any]
) -> None:
    async with api_client(
        tmp_path, RATE_LIMIT_JOBS_PER_HOUR="1"
    ) as client:
        primeiro = await client.post(
            f"{PREFIXO}/jobs",
            headers={"X-API-Key": CHAVE_A},
            **uploads_multipart,
        )
        assert primeiro.status_code == 202, primeiro.text

        segundo = await client.post(
            f"{PREFIXO}/jobs",
            headers={"X-API-Key": CHAVE_A},
            **uploads_multipart,
        )
        assert segundo.status_code == 429, segundo.text
        assert int(segundo.headers["Retry-After"]) > 0

        # O limite é por chave: outra chave continua podendo criar.
        outra = await client.post(
            f"{PREFIXO}/jobs",
            headers={"X-API-Key": CHAVE_B},
            **uploads_multipart,
        )
        assert outra.status_code == 202, outra.text


async def test_retorna_429_quando_limite_de_requisicoes_por_minuto_estourado(
    tmp_path: Path,
) -> None:
    limite = 3
    async with api_client(
        tmp_path, RATE_LIMIT_REQUESTS_PER_MINUTE=str(limite)
    ) as client:
        cabecalho = {"X-API-Key": CHAVE_A}
        for _ in range(limite):
            dentro = await client.get(
                f"{PREFIXO}/jobs/inexistente", headers=cabecalho
            )
            assert dentro.status_code == 404, dentro.text

        estourou = await client.get(
            f"{PREFIXO}/jobs/inexistente", headers=cabecalho
        )

    assert estourou.status_code == 429
    assert int(estourou.headers["Retry-After"]) > 0
    assert estourou.headers["content-type"].startswith(
        "application/problem+json"
    )


# --------------------------------------------------------------------------
# Vazamento de informação e formato dos erros
# --------------------------------------------------------------------------


async def _coletar_respostas_de_erro(
    client: httpx.AsyncClient,
) -> dict[str, httpx.Response]:
    cabecalho = {"X-API-Key": CHAVE_A}
    return {
        "sem_chave": await client.get(f"{PREFIXO}/jobs/abc123"),
        "chave_invalida": await client.get(
            f"{PREFIXO}/jobs/abc123", headers={"X-API-Key": CHAVE_INVALIDA}
        ),
        "job_inexistente": await client.get(
            f"{PREFIXO}/jobs/naoexiste123", headers=cabecalho
        ),
        "identificador_invalido": await client.get(
            f"{PREFIXO}/jobs/id~invalido!", headers=cabecalho
        ),
        "rota_inexistente": await client.get(f"{PREFIXO}/nao-existe"),
        "metodo_errado": await client.put(
            f"{PREFIXO}/jobs/abc123", headers=cabecalho
        ),
        "arquivo_nao_e_video": await client.post(
            f"{PREFIXO}/jobs",
            headers=cabecalho,
            files={"file": ("x.mp4", b"lixo binario" * 50, "video/mp4")},
            data={"num_variations": "1"},
        ),
        "num_variations_absurdo": await client.post(
            f"{PREFIXO}/jobs",
            headers=cabecalho,
            files={"file": ("x.mp4", b"lixo binario" * 50, "video/mp4")},
            data={"num_variations": "9999"},
        ),
        "corpo_ausente": await client.post(f"{PREFIXO}/jobs", headers=cabecalho),
        "download_zip_inexistente": await client.get(
            f"{PREFIXO}/jobs/naoexiste123/download", headers=cabecalho
        ),
    }


async def test_nenhuma_resposta_de_erro_vaza_detalhe_interno(
    tmp_path: Path,
) -> None:
    """Varre vários erros procurando caminho absoluto, traceback ou .py."""
    async with api_client(tmp_path) as client:
        respostas = await _coletar_respostas_de_erro(client)

    vazamentos: list[str] = []
    for nome, resposta in respostas.items():
        assert resposta.status_code >= 400, f"{nome} não é erro"
        corpo = resposta.text
        for marcador in MARCADORES_INTERNOS:
            if marcador in corpo:
                vazamentos.append(f"{nome} contém {marcador!r}: {corpo[:300]}")
        if str(tmp_path) in corpo:
            vazamentos.append(f"{nome} contém o caminho do storage")

    assert vazamentos == [], "\n".join(vazamentos)


# Erros levantados pela própria aplicação (ProblemError). Os erros gerados
# pelo framework (rota inexistente, método errado, validação de corpo) são
# checados à parte, porque não passam pelo handler de problem+json.
ERROS_DA_APLICACAO = (
    "sem_chave",
    "chave_invalida",
    "job_inexistente",
    "identificador_invalido",
    "arquivo_nao_e_video",
    "num_variations_absurdo",
    "download_zip_inexistente",
)


async def test_respostas_de_erro_seguem_problem_json(tmp_path: Path) -> None:
    async with api_client(tmp_path) as client:
        todas = await _coletar_respostas_de_erro(client)
    respostas = {nome: todas[nome] for nome in ERROS_DA_APLICACAO}

    fora_do_padrao: list[str] = []
    for nome, resposta in respostas.items():
        tipo = resposta.headers.get("content-type", "")
        if not tipo.startswith("application/problem+json"):
            fora_do_padrao.append(f"{nome}: content-type {tipo!r}")
            continue
        corpo = _corpo_problem(resposta)
        faltando = {"type", "title", "status", "detail"} - set(corpo)
        if faltando:
            fora_do_padrao.append(f"{nome}: faltam campos {sorted(faltando)}")
        elif corpo["status"] != resposta.status_code:
            fora_do_padrao.append(
                f"{nome}: status do corpo {corpo['status']} != "
                f"{resposta.status_code}"
            )

    assert fora_do_padrao == [], "\n".join(fora_do_padrao)


async def test_erro_de_validacao_segue_problem_json_quando_corpo_ausente(
    tmp_path: Path,
) -> None:
    """POST sem arquivo: o contrato (ADR-005/002) diz problem+json para erro.

    Hoje o FastAPI responde 422 em application/json com `detail` como lista
    de objetos — um cliente que lê `detail` como texto quebra.
    """
    async with api_client(tmp_path) as client:
        resposta = await client.post(
            f"{PREFIXO}/jobs", headers={"X-API-Key": CHAVE_A}
        )

    assert resposta.status_code >= 400
    assert resposta.headers["content-type"].startswith(
        "application/problem+json"
    ), f"content-type inesperado: {resposta.headers.get('content-type')}"
    assert {"type", "title", "status", "detail"} <= set(resposta.json())


# --------------------------------------------------------------------------
# Startup seguro
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("descricao", "api_keys"),
    [
        ("vazio", ""),
        ("so_virgulas", " , , "),
        ("chave_de_exemplo", "troque-esta-chave"),
        ("chave_curta", "abc123"),
        ("uma_boa_e_uma_curta", f"{CHAVE_A},curta"),
    ],
)
async def test_startup_recusado_quando_api_keys_e_fraca(
    tmp_path: Path, descricao: str, api_keys: str
) -> None:
    """Subir sem chave forte equivale a subir sem autenticação nenhuma."""
    with pytest.raises(RuntimeError):
        await _iniciar_app(tmp_path, API_KEYS=api_keys)


async def test_startup_aceito_quando_api_keys_e_forte(tmp_path: Path) -> None:
    await _iniciar_app(tmp_path, API_KEYS=CHAVE_A)
