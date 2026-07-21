"""Testes da orquestração concorrente do lote (`core.batch`).

Estratégia para medir concorrência real
---------------------------------------
Medir paralelismo pelo tempo total (comparar duração com e sem semáforo) é
frágil: depende da carga da máquina e produz flake em CI. A abordagem usada
aqui é observar diretamente os processos de FFmpeg.

Para isso, `core.ffmpeg.find_binary` é apontado para um wrapper `/bin/sh`
que registra START/END num log e chama o FFmpeg de verdade. Nada do código
sob teste é substituído: `render_batch`, `render_variation`, o semáforo e o
subprocesso continuam sendo os reais — só o *caminho do binário* muda, o que
é instrumentação do ambiente, não mock da lógica. Do log de eventos sai o
pico exato de renders simultâneos, sem depender de cronômetro.

No teste de cancelamento o wrapper NÃO é usado: lá interessa o FFmpeg real,
localizado com `pgrep -f`, para provar que não sobrou processo órfão.
"""

from __future__ import annotations

import asyncio
import subprocess
import uuid
from pathlib import Path

import pytest

from ads_varietor.core import ffmpeg as ffmpeg_module
from ads_varietor.core.batch import render_batch, summarize
from ads_varietor.core.models import (
    VariationParams,
    VariationResult,
    VariationStatus,
    VideoInfo,
)
from ads_varietor.core.probe import find_binary

# --------------------------------------------------------------------------
# Helpers e fixtures
# --------------------------------------------------------------------------

LARGURA_CURTO = 320
ALTURA_CURTO = 240
DURACAO_CURTO = 1.0


def _make_video(
    destination: Path,
    *,
    width: int = LARGURA_CURTO,
    height: int = ALTURA_CURTO,
    duration: float = DURACAO_CURTO,
) -> Path:
    """Gera um vídeo sintético barato com ffmpeg."""
    command = [
        find_binary("ffmpeg"),
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=s={width}x{height}:d={duration}",
        "-f",
        "lavfi",
        "-i",
        f"sine=f=440:d={duration}",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-y",
        str(destination),
    ]
    subprocess.run(command, check=True, capture_output=True, timeout=120)
    return destination


@pytest.fixture(scope="session")
def video_curto(tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = tmp_path_factory.mktemp("batch_video_curto")
    return _make_video(directory / "curto.mp4")


@pytest.fixture(scope="session")
def video_pesado(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Grande o bastante para o encode não caber em 1 segundo.

    A margem é folgada porque o filtergraph passou a usar `crop` no lugar de
    `pad` + composição e ficou bem mais rápido.
    """
    directory = tmp_path_factory.mktemp("batch_video_pesado")
    return _make_video(
        directory / "pesado.mp4", width=1920, height=1080, duration=90.0
    )


def _info_curto() -> VideoInfo:
    """Metadados do `video_curto`, para pular o ffprobe onde ele não importa."""
    return VideoInfo(
        width=LARGURA_CURTO,
        height=ALTURA_CURTO,
        duration_seconds=DURACAO_CURTO,
        has_audio=True,
        video_codec="h264",
    )


def _params(variation_id: str, **overrides: object) -> VariationParams:
    return VariationParams(variation_id=variation_id, **overrides)  # type: ignore[arg-type]


def _lista_de_params(quantidade: int, prefixo: str = "var") -> list[VariationParams]:
    return [_params(f"{prefixo}_{indice}") for indice in range(quantidade)]


def _instalar_ffmpeg_instrumentado(
    monkeypatch: pytest.MonkeyPatch,
    diretorio: Path,
    *,
    falhar_para: str | None = None,
) -> Path:
    """Aponta `core.ffmpeg.find_binary` para um wrapper que loga START/END.

    Se `falhar_para` for passado, o wrapper sai com código 1 quando o id da
    variação aparece nos argumentos — jeito de provocar uma falha real de
    render sem tocar em nada de produção.
    """
    log = diretorio / "eventos.log"
    wrapper = diretorio / "ffmpeg_instrumentado.sh"
    ffmpeg_real = find_binary("ffmpeg")

    falha = ""
    if falhar_para is not None:
        falha = (
            f'case "$*" in\n'
            f"  *{falhar_para}*)\n"
            f'    printf "END\\n" >> "{log}"\n'
            f"    exit 1\n"
            f"    ;;\n"
            f"esac\n"
        )

    wrapper.write_text(
        "#!/bin/sh\n"
        # Uma linha curta por evento: write(2) com O_APPEND é atômico nesse
        # tamanho, então processos concorrentes não embaralham o log.
        f'printf "START\\n" >> "{log}"\n'
        f"{falha}"
        f'"{ffmpeg_real}" "$@"\n'
        "codigo=$?\n"
        f'printf "END\\n" >> "{log}"\n'
        "exit $codigo\n"
    )
    wrapper.chmod(0o755)

    def _fake_find_binary(nome: str) -> str:
        return str(wrapper) if nome == "ffmpeg" else find_binary(nome)

    monkeypatch.setattr(ffmpeg_module, "find_binary", _fake_find_binary)
    return log


def _pico_de_concorrencia(log: Path) -> int:
    """Maior número de FFmpegs vivos ao mesmo tempo, segundo o log."""
    ativos = 0
    pico = 0
    for linha in log.read_text().splitlines():
        if linha == "START":
            ativos += 1
            pico = max(pico, ativos)
        elif linha == "END":
            ativos -= 1
    return pico


def _ffmpegs_vivos(marcador: str) -> list[str]:
    """PIDs de processos cuja linha de comando contém o marcador."""
    resultado = subprocess.run(
        ["pgrep", "-f", marcador], capture_output=True, text=True, timeout=15
    )
    return [pid for pid in resultado.stdout.split() if pid]


# --------------------------------------------------------------------------
# Casos triviais de entrada
# --------------------------------------------------------------------------


async def test_devolve_lista_vazia_quando_nao_ha_variacoes(tmp_path: Path) -> None:
    """Sem variações não deve haver probe nem criação de diretório.

    O vídeo apontado nem existe: se `render_batch` tentasse fazer o ffprobe,
    o teste explodiria.
    """
    saida = tmp_path / "saida"

    resultados = await render_batch(
        input_video=tmp_path / "nao_existe.mp4",
        output_dir=saida,
        variations=[],
    )

    assert resultados == []
    assert not saida.exists()


# --------------------------------------------------------------------------
# Renderização do lote
# --------------------------------------------------------------------------


async def test_renderiza_todas_na_ordem_de_entrada_quando_lote_tem_varias(
    video_curto: Path, tmp_path: Path
) -> None:
    """Um resultado por variação, na mesma ordem, com arquivo em disco.

    Aqui `info` fica de fora de propósito, para exercitar o ffprobe interno.
    """
    saida = tmp_path / "saida"
    variacoes = [
        _params("var_a", video_scale=1.0),
        _params("var_b", video_scale=1.05),
        _params("var_c", speed=1.5),
    ]

    resultados = await render_batch(
        input_video=video_curto,
        output_dir=saida,
        variations=variacoes,
        timeout_seconds=120,
    )

    assert [item.variation_id for item in resultados] == ["var_a", "var_b", "var_c"]
    assert all(item.status is VariationStatus.COMPLETED for item in resultados), [
        item.error for item in resultados
    ]
    for item in resultados:
        assert item.output_path is not None
        arquivo = Path(item.output_path)
        assert arquivo.parent == saida
        assert arquivo.stat().st_size > 0
        assert item.size_bytes == arquivo.stat().st_size


async def test_on_result_e_chamado_por_variacao_antes_do_lote_terminar(
    video_curto: Path, tmp_path: Path
) -> None:
    """Progresso precisa chegar durante o lote, não só no fim."""
    recebidos: list[str] = []
    primeiro_resultado = asyncio.Event()

    async def on_result(resultado: VariationResult) -> None:
        recebidos.append(resultado.variation_id)
        primeiro_resultado.set()

    variacoes = _lista_de_params(3)
    # Semáforo de 1 garante que ainda restam dois renders quando o primeiro
    # on_result dispara.
    task = asyncio.create_task(
        render_batch(
            input_video=video_curto,
            output_dir=tmp_path / "saida",
            variations=variacoes,
            info=_info_curto(),
            timeout_seconds=120,
            on_result=on_result,
            semaphore=asyncio.Semaphore(1),
        )
    )

    await asyncio.wait_for(primeiro_resultado.wait(), timeout=120)
    assert not task.done(), "o lote terminou antes do primeiro callback"
    parcial = list(recebidos)
    assert len(parcial) < len(variacoes)

    resultados = await task

    assert recebidos == [item.variation_id for item in resultados]
    assert len(recebidos) == len(variacoes)
    assert parcial == recebidos[: len(parcial)]


# --------------------------------------------------------------------------
# Regressão: o semáforo de quem chama é o limite efetivo
# --------------------------------------------------------------------------


async def test_nunca_passa_de_um_render_simultaneo_quando_semaforo_e_de_um(
    video_curto: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = _instalar_ffmpeg_instrumentado(monkeypatch, tmp_path)

    resultados = await render_batch(
        input_video=video_curto,
        output_dir=tmp_path / "saida",
        variations=_lista_de_params(4),
        info=_info_curto(),
        timeout_seconds=120,
        # max_concurrent alto de propósito: quem manda é o semáforo.
        max_concurrent=8,
        semaphore=asyncio.Semaphore(1),
    )

    assert all(item.status is VariationStatus.COMPLETED for item in resultados)
    assert _pico_de_concorrencia(log) == 1


async def test_nunca_passa_de_tres_renders_simultaneos_quando_semaforo_e_de_tres(
    video_curto: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = _instalar_ffmpeg_instrumentado(monkeypatch, tmp_path)

    resultados = await render_batch(
        input_video=video_curto,
        output_dir=tmp_path / "saida",
        variations=_lista_de_params(6),
        info=_info_curto(),
        timeout_seconds=120,
        max_concurrent=1,
        semaphore=asyncio.Semaphore(3),
    )

    assert all(item.status is VariationStatus.COMPLETED for item in resultados)
    pico = _pico_de_concorrencia(log)
    assert pico <= 3, f"o semáforo de 3 foi furado: pico de {pico}"
    # Prova que houve paralelismo de verdade — uma implementação serial
    # (ou que ignorasse o semáforo usando max_concurrent=1) daria pico 1.
    assert pico >= 2, f"nenhum paralelismo observado: pico de {pico}"


async def test_dois_lotes_concorrentes_respeitam_o_limite_somado_do_semaforo(
    video_curto: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regressão: com semáforo por job, dois lotes abriam 2x o limite."""
    log = _instalar_ffmpeg_instrumentado(monkeypatch, tmp_path)
    compartilhado = asyncio.Semaphore(2)

    async def lote(nome: str) -> list[VariationResult]:
        return await render_batch(
            input_video=video_curto,
            output_dir=tmp_path / nome,
            variations=_lista_de_params(4, prefixo=nome),
            info=_info_curto(),
            timeout_seconds=120,
            max_concurrent=8,
            semaphore=compartilhado,
        )

    primeiro, segundo = await asyncio.gather(lote("lotea"), lote("loteb"))

    assert len(primeiro) == 4
    assert len(segundo) == 4
    assert all(
        item.status is VariationStatus.COMPLETED for item in primeiro + segundo
    )
    pico = _pico_de_concorrencia(log)
    assert pico <= 2, f"os dois lotes somados furaram o limite: pico de {pico}"
    assert pico >= 2, f"nenhum paralelismo observado: pico de {pico}"


async def test_max_concurrent_limita_quando_nenhum_semaforo_e_passado(
    video_curto: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    serial_dir = tmp_path / "serial"
    serial_dir.mkdir(parents=True, exist_ok=True)
    log_serial = _instalar_ffmpeg_instrumentado(monkeypatch, serial_dir)

    await render_batch(
        input_video=video_curto,
        output_dir=tmp_path / "saida_serial",
        variations=_lista_de_params(4, prefixo="serial"),
        info=_info_curto(),
        timeout_seconds=120,
        max_concurrent=1,
    )
    assert _pico_de_concorrencia(log_serial) == 1

    paralelo_dir = tmp_path / "paralelo"
    paralelo_dir.mkdir(parents=True, exist_ok=True)
    log_paralelo = _instalar_ffmpeg_instrumentado(monkeypatch, paralelo_dir)

    await render_batch(
        input_video=video_curto,
        output_dir=tmp_path / "saida_paralela",
        variations=_lista_de_params(6, prefixo="paralelo"),
        info=_info_curto(),
        timeout_seconds=120,
        max_concurrent=3,
    )
    pico = _pico_de_concorrencia(log_paralelo)
    assert pico <= 3, f"max_concurrent=3 foi furado: pico de {pico}"
    assert pico >= 2, f"max_concurrent não liberou paralelismo: pico de {pico}"


# --------------------------------------------------------------------------
# Cancelamento
# --------------------------------------------------------------------------


async def test_nao_deixa_ffmpeg_orfao_quando_a_task_do_lote_e_cancelada(
    video_pesado: Path, tmp_path: Path
) -> None:
    """Cancelar o lote precisa matar os filhos, não só soltar a task."""
    marcador = f"cancel_{uuid.uuid4().hex[:10]}"
    saida = tmp_path / "saida"
    variacoes = [_params(f"{marcador}_{indice}") for indice in range(3)]

    task = asyncio.create_task(
        render_batch(
            input_video=video_pesado,
            output_dir=saida,
            variations=variacoes,
            info=VideoInfo(
                width=1280,
                height=720,
                duration_seconds=10.0,
                has_audio=True,
                video_codec="h264",
            ),
            timeout_seconds=300,
            semaphore=asyncio.Semaphore(3),
        )
    )

    # Espera os processos de FFmpeg realmente existirem antes de cancelar.
    for _ in range(200):
        if _ffmpegs_vivos(marcador):
            break
        await asyncio.sleep(0.05)
    else:  # pragma: no cover - só acontece se o render nem começar
        task.cancel()
        pytest.fail("nenhum processo de ffmpeg apareceu antes do cancelamento")

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # Tolerância curta para o SIGTERM ser processado.
    for _ in range(30):
        sobrando = _ffmpegs_vivos(marcador)
        if not sobrando:
            break
        await asyncio.sleep(0.1)
    else:
        pytest.fail(f"ffmpeg órfão após o cancelamento: pids {sobrando}")

    assert list(saida.glob("*.mp4")) == []


# --------------------------------------------------------------------------
# Falhas isoladas
# --------------------------------------------------------------------------


async def test_lote_termina_com_as_demais_concluidas_quando_uma_variacao_falha(
    video_curto: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Uma variação com erro de encode não pode derrubar as irmãs."""
    _instalar_ffmpeg_instrumentado(monkeypatch, tmp_path, falhar_para="var_ruim")
    recebidos: list[str] = []

    async def on_result(resultado: VariationResult) -> None:
        recebidos.append(resultado.variation_id)

    variacoes = [_params("var_boa_1"), _params("var_ruim"), _params("var_boa_2")]
    resultados = await render_batch(
        input_video=video_curto,
        output_dir=tmp_path / "saida",
        variations=variacoes,
        info=_info_curto(),
        timeout_seconds=120,
        semaphore=asyncio.Semaphore(2),
        on_result=on_result,
    )

    por_id = {item.variation_id: item for item in resultados}
    assert [item.variation_id for item in resultados] == [
        "var_boa_1",
        "var_ruim",
        "var_boa_2",
    ]
    assert por_id["var_ruim"].status is VariationStatus.FAILED
    assert por_id["var_ruim"].output_path is None
    assert por_id["var_boa_1"].status is VariationStatus.COMPLETED
    assert por_id["var_boa_2"].status is VariationStatus.COMPLETED
    assert not (tmp_path / "saida" / "var_ruim.mp4").exists()
    assert sorted(recebidos) == ["var_boa_1", "var_boa_2", "var_ruim"]


async def test_lote_devolve_falha_por_variacao_quando_timeout_estoura(
    video_pesado: Path, tmp_path: Path
) -> None:
    """Timeout curto num vídeo grande: falha real, sem exceção e sem lixo."""
    saida = tmp_path / "saida"
    resultados = await render_batch(
        input_video=video_pesado,
        output_dir=saida,
        variations=_lista_de_params(2, prefixo="lento"),
        info=VideoInfo(
            width=1280,
            height=720,
            duration_seconds=10.0,
            has_audio=True,
            video_codec="h264",
        ),
        timeout_seconds=1,
        semaphore=asyncio.Semaphore(2),
    )

    assert len(resultados) == 2
    for item in resultados:
        assert item.status is VariationStatus.FAILED
        assert item.error is not None
        assert "excedido" in item.error
    assert list(saida.glob("*.mp4")) == []


# --------------------------------------------------------------------------
# summarize
# --------------------------------------------------------------------------


def _resultado(variation_id: str, status: VariationStatus) -> VariationResult:
    return VariationResult(variation_id=variation_id, status=status)


def test_summarize_zera_tudo_quando_nao_ha_resultados() -> None:
    assert summarize([]) == {"total": 0, "completed": 0, "failed": 0}


def test_summarize_separa_concluidas_de_falhas_quando_lote_e_misto() -> None:
    resultados = [
        _resultado("a", VariationStatus.COMPLETED),
        _resultado("b", VariationStatus.FAILED),
        _resultado("c", VariationStatus.COMPLETED),
        _resultado("d", VariationStatus.FAILED),
        _resultado("e", VariationStatus.COMPLETED),
    ]
    assert summarize(resultados) == {"total": 5, "completed": 3, "failed": 2}


def test_summarize_conta_pendentes_como_falha_quando_status_nao_e_completed() -> None:
    """Só COMPLETED conta como sucesso; o resto entra em `failed`."""
    resultados = [
        _resultado("a", VariationStatus.PENDING),
        _resultado("b", VariationStatus.RUNNING),
        _resultado("c", VariationStatus.COMPLETED),
    ]
    assert summarize(resultados) == {"total": 3, "completed": 1, "failed": 2}
