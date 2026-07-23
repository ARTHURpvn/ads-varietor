"""Testes do filtergraph, da montagem do comando e do render do FFmpeg."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from ads_varietor.core.ffmpeg import (
    build_command,
    build_filter_complex,
    render_variation,
)
from ads_varietor.core.models import (
    FilterType,
    VariationParams,
    VariationStatus,
    VideoInfo,
)
from ads_varietor.core.probe import find_binary

# --------------------------------------------------------------------------
# Helpers e fixtures
# --------------------------------------------------------------------------


def _make_video(
    destination: Path,
    *,
    width: int = 320,
    height: int = 240,
    duration: float = 2.0,
    with_audio: bool = True,
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
    ]
    if with_audio:
        command += ["-f", "lavfi", "-i", f"sine=f=440:d={duration}"]
    command += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]
    if with_audio:
        command += ["-c:a", "aac"]
    command += ["-y", str(destination)]
    subprocess.run(command, check=True, capture_output=True, timeout=120)
    return destination


def _ffprobe(path: Path) -> dict:
    output = subprocess.run(
        [
            find_binary("ffprobe"),
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )
    return json.loads(output.stdout)


def _info(
    *,
    width: int = 320,
    height: int = 240,
    duration: float = 2.0,
    has_audio: bool = True,
) -> VideoInfo:
    return VideoInfo(
        width=width,
        height=height,
        duration_seconds=duration,
        has_audio=has_audio,
        video_codec="h264",
    )


def _params(**overrides) -> VariationParams:
    base = {"variation_id": "var_01"}
    base.update(overrides)
    return VariationParams(**base)


def _chain_with(graph: str, needle: str) -> str:
    """Devolve o elo do filtergraph que contém `needle`."""
    matches = [chain for chain in graph.split(";") if needle in chain]
    assert matches, f"nenhum elo contém {needle!r} em: {graph}"
    return matches[0]


@pytest.fixture(scope="session")
def video_com_audio(tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = tmp_path_factory.mktemp("fixture_video_audio")
    return _make_video(directory / "com_audio.mp4", with_audio=True)


@pytest.fixture(scope="session")
def video_sem_audio(tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = tmp_path_factory.mktemp("fixture_video_mudo")
    return _make_video(directory / "sem_audio.mp4", with_audio=False)


@pytest.fixture(scope="session")
def video_pesado(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Vídeo grande o bastante para o encode não terminar em 1 segundo.

    A margem é generosa de propósito: o filtergraph passou a usar `crop` no
    lugar de `pad` + composição, o que deixou o encode bem mais rápido e fez
    a versão anterior desta fixture (15s) terminar antes do timeout.
    """
    directory = tmp_path_factory.mktemp("fixture_video_pesado")
    return _make_video(
        directory / "pesado.mp4", width=1920, height=1080, duration=90.0
    )


# --------------------------------------------------------------------------
# Enquadramento e camada de cor
# --------------------------------------------------------------------------


def test_grafo_corta_o_centro_e_amplia_quando_a_escala_passa_de_um() -> None:
    """Corta a região central e amplia de volta, preservando a resolução.

    A ordem importa por custo: cortar antes faz o scaler processar menos
    pixels que o original, em vez de mais.
    """
    graph, _ = build_filter_complex(
        _params(video_scale=1.05), _info(width=640, height=480)
    )

    assert "crop=608:456" in graph
    assert "scale=640:480" in graph
    assert graph.index("crop=") < graph.index("scale=640:480")


def test_grafo_nao_usa_pad_para_nao_deixar_faixa_de_fundo() -> None:
    graph, _ = build_filter_complex(
        _params(video_scale=1.05), _info(width=640, height=480)
    )

    assert "pad=" not in graph


def test_veu_de_cor_usa_drawbox_com_alpha_quando_ha_tint() -> None:
    """O véu é um `drawbox` com `color@alpha`, um blend real e sutil.

    Regressão: o `colorize` que estava aqui aplicava a cor cheia — o `mix`
    dele mexe no brilho, não na intensidade — e tingia o vídeo inteiro.
    """
    graph, _ = build_filter_complex(
        _params(tint_opacity=0.05, background_color="cc9977"),
        _info(width=640, height=480),
    )

    assert "drawbox=" in graph
    assert "color=0xcc9977@0.0500" in graph
    # O colorize quebrado não pode voltar, e nada de segundo stream de vídeo.
    assert "colorize=" not in graph
    assert "color=c=" not in graph
    assert "overlay=0:0" not in graph


def test_nenhuma_camada_de_cor_e_criada_quando_tint_e_zero() -> None:
    graph, _ = build_filter_complex(
        _params(tint_opacity=0.0), _info(width=640, height=480)
    )

    assert "colorchannelmixer" not in graph


# --------------------------------------------------------------------------
# build_filter_complex — mapeamento de filtros
# --------------------------------------------------------------------------


def test_nenhum_filtro_de_cor_e_aplicado_quando_filter_type_e_none() -> None:
    graph, _ = build_filter_complex(_params(filter_type=FilterType.NONE), _info())
    assert "eq=" not in graph
    assert "hue=" not in graph


def test_brightness_vira_eq_com_valor_deslocado_quando_filtro_e_brightness() -> None:
    """eq aceita brightness em -1..1, então 1.5 vira 0.5."""
    graph, _ = build_filter_complex(
        _params(filter_type=FilterType.BRIGHTNESS, filter_value=1.5), _info()
    )
    assert "eq=brightness=0.5000" in graph

    graph_escuro, _ = build_filter_complex(
        _params(filter_type=FilterType.BRIGHTNESS, filter_value=0.25), _info()
    )
    assert "eq=brightness=-0.7500" in graph_escuro


def test_contrast_vira_eq_contrast_quando_filtro_e_contrast() -> None:
    graph, _ = build_filter_complex(
        _params(filter_type=FilterType.CONTRAST, filter_value=1.25), _info()
    )
    assert "eq=contrast=1.2500" in graph


def test_saturate_vira_eq_saturation_quando_filtro_e_saturate() -> None:
    graph, _ = build_filter_complex(
        _params(filter_type=FilterType.SATURATE, filter_value=0.75), _info()
    )
    assert "eq=saturation=0.7500" in graph


def test_hue_vira_deslocamento_em_graus_quando_filtro_e_hue() -> None:
    """hue=h recebe graus: (valor - 1) * 180."""
    graph, _ = build_filter_complex(
        _params(filter_type=FilterType.HUE, filter_value=1.5), _info()
    )
    assert "hue=h=90.0000" in graph

    graph_negativo, _ = build_filter_complex(
        _params(filter_type=FilterType.HUE, filter_value=0.5), _info()
    )
    assert "hue=h=-90.0000" in graph_negativo


@pytest.mark.parametrize("filter_type", list(FilterType))
def test_filtergraph_e_aceito_pelo_ffmpeg_quando_qualquer_filtro_e_usado(
    filter_type: FilterType, tmp_path: Path
) -> None:
    """Cada FilterType precisa gerar sintaxe que o FFmpeg realmente parseia."""
    video = _make_video(tmp_path / "in.mp4", duration=1.0)
    params = _params(filter_type=filter_type, filter_value=1.3)
    command = build_command(
        ffmpeg_path=find_binary("ffmpeg"),
        input_video=video,
        output_path=tmp_path / "out.mp4",
        params=params,
        info=_info(duration=1.0),
    )
    result = subprocess.run(command, capture_output=True, timeout=120)
    assert result.returncode == 0, result.stderr.decode()


def test_velocidade_vira_setpts_e_atempo_quando_speed_e_alterado() -> None:
    graph, _ = build_filter_complex(_params(speed=1.5), _info(has_audio=True))
    assert "setpts=PTS/1.500000" in graph
    assert "atempo=1.500000" in graph


# --------------------------------------------------------------------------
# build_filter_complex — dimensões pares
# --------------------------------------------------------------------------


def test_dimensoes_do_canvas_sao_pares_quando_original_e_impar() -> None:
    """Regressão: sem zoom, um lado ímpar chegava assim ao libx264."""
    graph, _ = build_filter_complex(_params(), _info(width=321, height=241))
    assert "crop=320:240" in graph


def _make_video_de_qualquer_dimensao(
    destination: Path, *, width: int, height: int, duration: float = 0.4
) -> Path:
    """Gera um vídeo mesmo com lado ímpar.

    libx264 com yuv420p não aceita dimensão ímpar nem na entrada, então a
    fonte usa ffv1/yuv444p — assim o único encode que pode reclamar de
    dimensão ímpar é o da saída, que é justamente o que se quer testar.
    """
    subprocess.run(
        [
            find_binary("ffmpeg"),
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=s={width}x{height}:r=5:d={duration}",
            "-c:v",
            "ffv1",
            "-pix_fmt",
            "yuv444p",
            "-y",
            str(destination),
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )
    return destination


def _dimensoes_declaradas(graph: str) -> list[tuple[int, int]]:
    """Lê as dimensões pedidas percorrendo o grafo filtro a filtro.

    Em vez de casar um padrão contra o texto inteiro, separa cada filtro,
    descarta os rótulos de entrada/saída e lê os argumentos: `s=LxA` das
    fontes e os dois primeiros argumentos de `scale`. Valores automáticos
    (-1, -2) são ignorados — quem decide a paridade ali é o FFmpeg.
    """
    dimensoes: list[tuple[int, int]] = []
    for elo in graph.split(";"):
        sem_rotulos = re.sub(r"\[[^\]]*\]", " ", elo)
        for filtro in sem_rotulos.split(","):
            nome, _, argumentos = filtro.strip().partition("=")
            # `crop` entra junto de `scale`: com zoom, é ele quem define o
            # recorte; sem zoom, é o único filtro que ajusta a dimensão de
            # uma entrada com lado ímpar.
            if nome in {"scale", "crop"}:
                partes = argumentos.split(":")[:2]
                if len(partes) == 2 and all(p.lstrip("-").isdigit() for p in partes):
                    largura, altura = int(partes[0]), int(partes[1])
                    if largura > 0 and altura > 0:
                        dimensoes.append((largura, altura))
            else:
                for argumento in argumentos.split(":"):
                    chave, _, valor = argumento.partition("=")
                    tamanho = re.fullmatch(r"(\d+)x(\d+)", valor)
                    if chave == "s" and tamanho is not None:
                        dimensoes.append(
                            (int(tamanho.group(1)), int(tamanho.group(2)))
                        )
    return dimensoes


@pytest.mark.parametrize(
    ("width", "height", "scale"),
    [
        (321, 241, 1.0),
        (1080, 1921, 1.33),
        (640, 480, 1.07),
        (33, 17, 1.5),
        (1920, 1080, 1.011),
    ],
)
def test_todas_as_dimensoes_geradas_sao_pares_quando_escala_e_arbitraria(
    width: int, height: int, scale: float, tmp_path: Path
) -> None:
    """libx264 com yuv420p rejeita largura ou altura ímpar.

    Além de conferir o que o grafo pede, o render acontece de verdade e a
    resolução final é lida com ffprobe: se o cálculo produzir lado ímpar, o
    encode falha e não existe saída para medir.
    """
    graph, _ = build_filter_complex(
        _params(video_scale=scale), _info(width=width, height=height)
    )
    declaradas = _dimensoes_declaradas(graph)
    assert declaradas, graph
    for largura, altura in declaradas:
        assert largura % 2 == 0, graph
        assert altura % 2 == 0, graph
        assert largura >= 2 and altura >= 2, graph

    entrada = _make_video_de_qualquer_dimensao(
        tmp_path / "in.mkv", width=width, height=height
    )
    saida = tmp_path / "out.mp4"
    comando = build_command(
        ffmpeg_path=find_binary("ffmpeg"),
        input_video=entrada,
        output_path=saida,
        params=_params(video_scale=scale),
        info=_info(width=width, height=height, duration=0.4, has_audio=False),
    )
    resultado = subprocess.run(comando, capture_output=True, timeout=120)
    assert resultado.returncode == 0, resultado.stderr.decode()

    stream = next(
        item for item in _ffprobe(saida)["streams"] if item["codec_type"] == "video"
    )
    # O canvas mantém a resolução original arredondada para baixo em par.
    assert (stream["width"], stream["height"]) == (
        width - width % 2,
        height - height % 2,
    )


def test_overlay_tem_largura_par_quando_escala_gera_valor_impar() -> None:
    graph, _ = build_filter_complex(
        _params(overlay_enabled=True, overlay_scale=0.33, overlay_opacity=0.5),
        _info(width=320, height=240),
        has_overlay_input=True,
    )
    elo = _chain_with(graph, "[1:v]")
    largura = int(re.search(r"scale=(\d+):-2", elo).group(1))
    assert largura % 2 == 0


# --------------------------------------------------------------------------
# build_filter_complex — áudio
# --------------------------------------------------------------------------


def test_nenhum_stream_de_audio_e_mapeado_quando_video_nao_tem_audio() -> None:
    graph, maps = build_filter_complex(_params(), _info(has_audio=False))
    assert maps == ["[vout]"]
    assert "[0:a]" not in graph
    assert "amix" not in graph


def test_audio_original_e_mapeado_quando_video_tem_audio() -> None:
    graph, maps = build_filter_complex(_params(), _info(has_audio=True))
    assert maps == ["[vout]", "[a_original]"]
    assert "[0:a]atempo=" in graph


def test_ruido_tem_duracao_limitada_quando_video_e_mudo() -> None:
    """Regressão: anoisesrc sem `d=` é infinita e trava o encode por horas."""
    info = _info(duration=2.0, has_audio=False)
    graph, maps = build_filter_complex(
        _params(noise_audio=True, noise_level=0.5), info
    )
    elo = _chain_with(graph, "anoisesrc")
    duracao = re.search(r":d=([0-9.]+)", elo)
    assert duracao is not None, elo
    valor = float(duracao.group(1))
    assert 0 < valor <= info.duration_seconds + 10
    assert maps == ["[vout]", "[a_noise]"]


def test_duracao_do_ruido_acompanha_a_velocidade_quando_video_e_desacelerado() -> None:
    graph, _ = build_filter_complex(
        _params(noise_audio=True, noise_level=0.5, speed=0.5),
        _info(duration=10.0, has_audio=False),
    )
    valor = float(re.search(r":d=([0-9.]+)", _chain_with(graph, "anoisesrc")).group(1))
    # 10s / 0.5 = 20s de saída, mais a margem de 2s.
    assert valor == pytest.approx(22.0, abs=0.01)


def test_ruido_tem_duracao_minima_quando_video_tem_duracao_zero() -> None:
    graph, _ = build_filter_complex(
        _params(noise_audio=True, noise_level=0.3),
        _info(duration=0.0, has_audio=False),
    )
    valor = float(re.search(r":d=([0-9.]+)", _chain_with(graph, "anoisesrc")).group(1))
    assert valor >= 1.0


def test_amix_combina_as_duas_fontes_quando_ha_audio_e_ruido() -> None:
    graph, maps = build_filter_complex(
        _params(noise_audio=True, noise_level=0.4), _info(has_audio=True)
    )
    assert "amix=inputs=2" in graph
    assert "[a_original][a_noise]amix" in graph
    assert maps == ["[vout]", "[aout]"]


def test_ruido_e_ignorado_quando_nivel_e_zero() -> None:
    graph, maps = build_filter_complex(
        _params(noise_audio=True, noise_level=0.0), _info(has_audio=False)
    )
    assert "anoisesrc" not in graph
    assert maps == ["[vout]"]


# --------------------------------------------------------------------------
# build_filter_complex — overlay
# --------------------------------------------------------------------------


def test_overlay_nao_entra_no_grafo_quando_nao_ha_segunda_entrada() -> None:
    graph, _ = build_filter_complex(
        _params(overlay_enabled=True, overlay_opacity=0.5),
        _info(),
        has_overlay_input=False,
    )
    assert "[1:v]" not in graph
    assert "[composed]setsar=1,format=yuv420p[vout]" in graph


def test_overlay_nao_entra_no_grafo_quando_flag_esta_desligada() -> None:
    graph, _ = build_filter_complex(
        _params(overlay_enabled=False), _info(), has_overlay_input=True
    )
    assert "[1:v]" not in graph


def test_overlay_usa_eof_action_pass_e_nao_shortest_quando_esta_ativo() -> None:
    """Regressão: shortest=1 no overlay truncava a saída na duração do overlay."""
    graph, _ = build_filter_complex(
        _params(overlay_enabled=True, overlay_opacity=0.6),
        _info(),
        has_overlay_input=True,
    )
    elo = _chain_with(graph, "[composed][ov]")
    assert "eof_action=pass" in elo
    assert "shortest" not in elo
    assert "[overlaid]setsar=1,format=yuv420p[vout]" in graph


# --------------------------------------------------------------------------
# build_command
# --------------------------------------------------------------------------


def test_comando_e_lista_de_strings_quando_montado(tmp_path: Path) -> None:
    command = build_command(
        ffmpeg_path="/usr/bin/ffmpeg",
        input_video=tmp_path / "in.mp4",
        output_path=tmp_path / "out.mp4",
        params=_params(),
        info=_info(),
    )
    assert isinstance(command, list)
    assert all(isinstance(item, str) for item in command)
    assert command[0] == "/usr/bin/ffmpeg"
    assert command[-1] == str(tmp_path / "out.mp4")
    assert "-filter_complex" in command


HOSTIL = 'a; rm -rf / | cat && $(whoami) `id` "aspas" \'x\'\nnova linha'


def test_metadado_hostil_vira_um_unico_argumento_quando_tem_sintaxe_de_shell(
    tmp_path: Path,
) -> None:
    """Nada vindo do usuário pode virar sintaxe de shell: execução é sem shell."""
    command = build_command(
        ffmpeg_path="/usr/bin/ffmpeg",
        input_video=tmp_path / "in.mp4",
        output_path=tmp_path / "out.mp4",
        params=_params(metadata_title=HOSTIL, metadata_author=HOSTIL),
        info=_info(),
    )
    assert command.count("-metadata") == 2
    assert f"title={HOSTIL}" in command
    assert f"artist={HOSTIL}" in command
    # O conteúdo hostil aparece apenas dentro dos dois argumentos de metadado.
    assert sum(1 for item in command if HOSTIL in item) == 2


def test_metadados_sao_omitidos_quando_nao_foram_informados(tmp_path: Path) -> None:
    command = build_command(
        ffmpeg_path="/usr/bin/ffmpeg",
        input_video=tmp_path / "in.mp4",
        output_path=tmp_path / "out.mp4",
        params=_params(),
        info=_info(),
    )
    assert "-metadata" not in command


def test_segunda_entrada_e_adicionada_quando_ha_overlay(tmp_path: Path) -> None:
    command = build_command(
        ffmpeg_path="/usr/bin/ffmpeg",
        input_video=tmp_path / "in.mp4",
        output_path=tmp_path / "out.mp4",
        params=_params(overlay_enabled=True, overlay_opacity=0.5),
        info=_info(),
        overlay_video=tmp_path / "ov.mp4",
    )
    assert command.count("-i") == 2
    assert str(tmp_path / "ov.mp4") in command


def test_segunda_entrada_e_ignorada_quando_overlay_esta_desligado(
    tmp_path: Path,
) -> None:
    command = build_command(
        ffmpeg_path="/usr/bin/ffmpeg",
        input_video=tmp_path / "in.mp4",
        output_path=tmp_path / "out.mp4",
        params=_params(overlay_enabled=False),
        info=_info(),
        overlay_video=tmp_path / "ov.mp4",
    )
    assert command.count("-i") == 1


def test_codec_de_audio_e_omitido_quando_saida_nao_tem_audio(tmp_path: Path) -> None:
    command = build_command(
        ffmpeg_path="/usr/bin/ffmpeg",
        input_video=tmp_path / "in.mp4",
        output_path=tmp_path / "out.mp4",
        params=_params(),
        info=_info(has_audio=False),
    )
    assert "-c:a" not in command
    assert command.count("-map") == 1


def test_codec_de_audio_e_incluido_quando_saida_tem_audio(tmp_path: Path) -> None:
    command = build_command(
        ffmpeg_path="/usr/bin/ffmpeg",
        input_video=tmp_path / "in.mp4",
        output_path=tmp_path / "out.mp4",
        params=_params(),
        info=_info(has_audio=True),
    )
    assert "-c:a" in command
    assert "-shortest" in command
    assert command.count("-map") == 2


# --------------------------------------------------------------------------
# render_variation — render real
# --------------------------------------------------------------------------


async def test_variacao_e_renderizada_quando_video_e_valido(
    video_com_audio: Path, tmp_path: Path
) -> None:
    """Render real: a saída precisa ter vídeo na resolução do original."""
    saida = tmp_path / "out"
    saida.mkdir()
    resultado = await render_variation(
        input_video=video_com_audio,
        output_dir=saida,
        params=_params(
            variation_id="var_render",
            filter_type=FilterType.BRIGHTNESS,
            filter_value=1.2,
            speed=1.25,
            metadata_title=HOSTIL,
        ),
        info=_info(width=320, height=240, duration=2.0, has_audio=True),
        timeout_seconds=180,
    )

    assert resultado.status is VariationStatus.COMPLETED, resultado.error
    assert resultado.error is None
    arquivo = Path(resultado.output_path)
    assert arquivo == saida / "var_render.mp4"
    assert resultado.size_bytes == arquivo.stat().st_size > 0

    streams = _ffprobe(arquivo)["streams"]
    video = next(item for item in streams if item["codec_type"] == "video")
    assert (video["width"], video["height"]) == (320, 240)
    assert any(item["codec_type"] == "audio" for item in streams)


async def test_saida_nao_tem_audio_quando_original_e_mudo(
    video_sem_audio: Path, tmp_path: Path
) -> None:
    saida = tmp_path / "out"
    saida.mkdir()
    resultado = await render_variation(
        input_video=video_sem_audio,
        output_dir=saida,
        params=_params(variation_id="var_mudo"),
        info=_info(width=320, height=240, duration=2.0, has_audio=False),
        timeout_seconds=180,
    )

    assert resultado.status is VariationStatus.COMPLETED, resultado.error
    streams = _ffprobe(Path(resultado.output_path))["streams"]
    assert not any(item["codec_type"] == "audio" for item in streams)


async def test_ruido_termina_junto_com_o_video_quando_original_e_mudo(
    video_sem_audio: Path, tmp_path: Path
) -> None:
    """Regressão: ruído de duração infinita fazia o encode rodar por horas."""
    saida = tmp_path / "out"
    saida.mkdir()
    resultado = await render_variation(
        input_video=video_sem_audio,
        output_dir=saida,
        params=_params(
            variation_id="var_ruido", noise_audio=True, noise_level=0.4
        ),
        info=_info(width=320, height=240, duration=2.0, has_audio=False),
        timeout_seconds=60,
    )

    assert resultado.status is VariationStatus.COMPLETED, resultado.error
    formato = _ffprobe(Path(resultado.output_path))["format"]
    assert float(formato["duration"]) < 6.0


async def test_variacao_falha_sem_arquivo_parcial_quando_entrada_e_invalida(
    tmp_path: Path,
) -> None:
    entrada = tmp_path / "nao_e_video.mp4"
    entrada.write_bytes(b"conteudo qualquer")
    saida = tmp_path / "out"
    saida.mkdir()

    resultado = await render_variation(
        input_video=entrada,
        output_dir=saida,
        params=_params(variation_id="var_invalida"),
        info=_info(),
        timeout_seconds=60,
    )

    assert resultado.status is VariationStatus.FAILED
    assert resultado.error
    assert resultado.output_path is None
    assert list(saida.iterdir()) == []


async def test_variacao_falha_sem_arquivo_parcial_quando_timeout_estoura(
    video_pesado: Path, tmp_path: Path
) -> None:
    """Regressão: o .mp4 truncado ficava no diretório após o timeout."""
    saida = tmp_path / "out"
    saida.mkdir()

    resultado = await render_variation(
        input_video=video_pesado,
        output_dir=saida,
        params=_params(variation_id="var_timeout"),
        info=_info(width=1920, height=1080, duration=15.0, has_audio=True),
        timeout_seconds=1,
    )

    assert resultado.status is VariationStatus.FAILED
    assert "excedido" in (resultado.error or "")
    assert resultado.output_path is None
    assert list(saida.iterdir()) == []
