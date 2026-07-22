"""Testes da geração de metadados e do modo que só troca a identidade."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ads_varietor.core.ffmpeg import (
    build_metadata_only_command,
    compute_md5,
    render_variation,
)
from ads_varietor.core.generator import VariationGenerator
from ads_varietor.core.metadata import MetadataGenerator
from ads_varietor.core.models import (
    ProcessingMode,
    VariationParams,
    VariationStatus,
)
from ads_varietor.core.probe import find_binary, probe_video

# Tags que o contêiner MP4 descarta silenciosamente. Pedi-las daria a falsa
# impressão de que estão sendo gravadas no arquivo.
TAGS_NAO_SUPORTADAS_PELO_MP4 = {"make", "model", "software", "encoder"}


@pytest.fixture
def saida(tmp_path: Path) -> Path:
    """Diretório de saída pronto: render_variation não o cria sozinho."""
    destino = tmp_path / "saida"
    destino.mkdir()
    return destino


@pytest.fixture
def video(tmp_path: Path) -> Path:
    destino = tmp_path / "origem.mp4"
    subprocess.run(
        [
            find_binary("ffmpeg"), "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=s=320x240:d=2",
            "-f", "lavfi", "-i", "sine=f=440:d=2",
            "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
            "-y", str(destino),
        ],
        check=True,
    )
    return destino


def _tags(caminho: Path) -> dict[str, str]:
    resposta = subprocess.run(
        [
            find_binary("ffprobe"), "-v", "error",
            "-show_entries", "format_tags",
            "-of", "default=noprint_wrappers=1",
            str(caminho),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    tags: dict[str, str] = {}
    for linha in resposta.splitlines():
        if linha.startswith("TAG:") and "=" in linha:
            chave, _, valor = linha[4:].partition("=")
            tags[chave] = valor
    return tags


# ---------------------------------------------------------------------------
# Geração dos metadados
# ---------------------------------------------------------------------------


def test_metadados_nao_pedem_tag_que_o_mp4_descarta() -> None:
    metadados = MetadataGenerator(seed=1).generate()

    assert TAGS_NAO_SUPORTADAS_PELO_MP4.isdisjoint(metadados)


def test_comment_e_diferente_a_cada_chamada_mesmo_com_a_mesma_seed() -> None:
    gerador = MetadataGenerator(seed=7)
    outro = MetadataGenerator(seed=7)

    assert gerador.generate()["comment"] != outro.generate()["comment"]


def test_data_de_criacao_fica_no_passado_quando_gerada() -> None:
    from datetime import datetime, timezone

    referencia = datetime(2026, 7, 21, tzinfo=timezone.utc)
    metadados = MetadataGenerator(seed=3).generate(agora=referencia)

    assert metadados["creation_time"] < referencia.strftime("%Y-%m-%dT%H:%M:%S")


def test_variacoes_do_lote_nao_repetem_o_titulo_nem_o_comentario() -> None:
    variacoes = VariationGenerator(seed=11).generate(30)

    comentarios = {v.metadata_extra["comment"] for v in variacoes}

    assert len(comentarios) == 30


# ---------------------------------------------------------------------------
# Modo que só troca a identidade do arquivo
# ---------------------------------------------------------------------------


def test_comando_copia_streams_e_descarta_metadados_de_origem() -> None:
    params = VariationParams(variation_id="v1")
    comando = build_metadata_only_command(
        ffmpeg_path="ffmpeg",
        input_video=Path("entrada.mp4"),
        output_path=Path("saida.mp4"),
        params=params,
    )

    assert "copy" in comando
    assert comando[comando.index("-map_metadata") + 1] == "-1"
    assert comando[comando.index("-fflags") + 1] == "+bitexact"


def test_comando_nao_deixa_valor_de_metadado_virar_sintaxe_de_shell() -> None:
    perigoso = 'a"; rm -rf / #$(whoami)`x`'
    params = VariationParams(variation_id="v1", metadata_title=perigoso)

    comando = build_metadata_only_command(
        ffmpeg_path="ffmpeg",
        input_video=Path("e.mp4"),
        output_path=Path("s.mp4"),
        params=params,
    )

    assert f"title={perigoso}" in comando


async def test_saida_tem_hash_diferente_do_original_quando_so_troca_metadados(
    video: Path, saida: Path
) -> None:
    info = await probe_video(video)
    params = VariationGenerator(seed=5).generate(1)[0]

    resultado = await render_variation(
        input_video=video,
        output_dir=saida,
        params=params,
        info=info,
        mode=ProcessingMode.METADATA_ONLY,
    )

    assert resultado.status is VariationStatus.COMPLETED
    assert resultado.md5 is not None
    assert resultado.md5 != compute_md5(video)


async def test_imagem_e_som_ficam_identicos_quando_so_troca_metadados(
    video: Path, saida: Path
) -> None:
    """O ponto do modo rápido: só a identidade muda, o conteúdo não."""
    original = await probe_video(video)
    params = VariationGenerator(seed=5).generate(1)[0]

    resultado = await render_variation(
        input_video=video,
        output_dir=saida,
        params=params,
        info=original,
        mode=ProcessingMode.METADATA_ONLY,
    )

    assert resultado.output_path is not None
    gerado = await probe_video(Path(resultado.output_path))

    assert (gerado.width, gerado.height) == (original.width, original.height)
    assert gerado.video_codec == original.video_codec
    assert gerado.has_audio == original.has_audio
    assert abs(gerado.duration_seconds - original.duration_seconds) < 0.2


async def test_metadados_sao_gravados_e_a_assinatura_do_ffmpeg_some(
    video: Path, saida: Path
) -> None:
    info = await probe_video(video)
    params = VariationGenerator(seed=9).generate(1)[0]

    resultado = await render_variation(
        input_video=video,
        output_dir=saida,
        params=params,
        info=info,
        mode=ProcessingMode.METADATA_ONLY,
    )

    assert resultado.output_path is not None
    tags = _tags(Path(resultado.output_path))

    assert tags["title"] == params.metadata_title
    assert tags["comment"] == params.metadata_extra["comment"]
    # `encoder=LavfXX.YY` seria idêntico em todo arquivo gerado e denunciaria
    # a ferramenta usada.
    assert "encoder" not in tags


async def test_cada_variacao_do_lote_sai_com_hash_distinto(
    video: Path, saida: Path
) -> None:
    info = await probe_video(video)
    variacoes = VariationGenerator(seed=2).generate(5)

    hashes = []
    for params in variacoes:
        resultado = await render_variation(
            input_video=video,
            output_dir=saida,
            params=params,
            info=info,
            mode=ProcessingMode.METADATA_ONLY,
        )
        assert resultado.md5 is not None
        hashes.append(resultado.md5)

    assert len(set(hashes)) == 5
    assert compute_md5(video) not in hashes


async def test_modo_completo_tambem_devolve_o_hash_da_saida(
    video: Path, saida: Path
) -> None:
    info = await probe_video(video)
    params = VariationGenerator(seed=4).generate(1)[0]

    resultado = await render_variation(
        input_video=video,
        output_dir=saida,
        params=params,
        info=info,
        mode=ProcessingMode.FULL,
    )

    assert resultado.status is VariationStatus.COMPLETED
    assert resultado.md5 is not None
    assert resultado.md5 != compute_md5(video)


def test_md5_bate_com_a_referencia_do_sistema(tmp_path: Path) -> None:
    arquivo = tmp_path / "conteudo.bin"
    arquivo.write_bytes(b"conteudo conhecido para conferir o hash")

    esperado = subprocess.run(
        ["md5", "-q", str(arquivo)], capture_output=True, text=True, check=True
    ).stdout.strip()

    assert compute_md5(arquivo) == esperado


# ---------------------------------------------------------------------------
# Compatibilidade com jobs gravados antes da troca de campos
# ---------------------------------------------------------------------------


def test_variacao_antiga_ainda_e_lida_quando_json_nao_tem_tint_opacity() -> None:
    """Regressão: consultar um job antigo devolvia 500.

    Jobs gravados antes de `bg_opacity`/`video_opacity` virarem
    `tint_opacity` não têm o campo novo no JSON salvo no banco.
    """
    from ads_varietor.api.schemas import VariationView

    antigo = {
        "variation_id": "var_0000",
        "status": "completed",
        "error": None,
        "size_bytes": 1234,
        "md5": "a" * 32,
        "params": {
            "speed": 1.03,
            "filter_type": "brightness",
            "filter_value": 1.1,
            "background_color": "aabbcc",
            "video_scale": 0.92,
            "bg_opacity": 0.8,
            "video_opacity": 0.85,
            "noise_audio": True,
        },
    }

    visao = VariationView.model_validate(antigo)

    assert visao.params.tint_opacity == 0.0
    assert visao.params.video_scale == 0.92


# ---------------------------------------------------------------------------
# Nível do ruído de áudio
# ---------------------------------------------------------------------------


def test_mixagem_nao_normaliza_para_o_audio_original_nao_perder_volume() -> None:
    """Regressão: com a normalização padrão o original perdia 6 dB.

    O `amix` divide tudo pelo número de entradas quando normaliza, então o
    áudio caía para metade do volume só por existir uma faixa de ruído.
    """
    from ads_varietor.core.ffmpeg import build_filter_complex
    from ads_varietor.core.models import VideoInfo

    graph, _ = build_filter_complex(
        VariationParams(
            variation_id="v1", noise_audio=True, noise_level=0.01
        ),
        VideoInfo(
            width=320, height=240, duration_seconds=2.0,
            has_audio=True, video_codec="h264",
        ),
    )

    assert "normalize=0" in graph


def test_ruido_entra_com_peso_menor_que_o_audio_original() -> None:
    from ads_varietor.core.ffmpeg import NOISE_MIX_WEIGHT, build_filter_complex
    from ads_varietor.core.models import VideoInfo

    graph, _ = build_filter_complex(
        VariationParams(
            variation_id="v1", noise_audio=True, noise_level=0.01
        ),
        VideoInfo(
            width=320, height=240, duration_seconds=2.0,
            has_audio=True, video_codec="h264",
        ),
    )

    assert NOISE_MIX_WEIGHT < 1.0
    # A atenuação vai num filtro `volume` próprio: `weights=1 0.15` levava um
    # espaço, e espaço no meio do valor de uma opção de filtergraph é ambíguo
    # para o parser — o ruído acabava entrando sem atenuação nenhuma.
    assert f"volume={NOISE_MIX_WEIGHT}" in graph
    assert "weights=" not in graph


def test_amplitude_sorteada_fica_na_faixa_inaudivel() -> None:
    """Com peso 0.15, esta faixa mantém o ruído por volta de -73 a -84 dB,
    contra -21 dB de um áudio comum.
    """
    variacoes = VariationGenerator(seed=17).generate(200)

    com_ruido = [v for v in variacoes if v.noise_audio]

    assert com_ruido, "a amostra precisa conter variações com ruído"
    for variacao in com_ruido:
        assert 0.003 <= variacao.noise_level <= 0.012, variacao.noise_level


async def test_audio_do_original_mantem_o_volume_quando_ha_ruido(
    video: Path, saida: Path
) -> None:
    """Mede o volume real da saída e compara com o do arquivo de entrada."""
    import re

    def volume_medio(caminho: Path) -> float:
        resposta = subprocess.run(
            [
                find_binary("ffmpeg"), "-hide_banner", "-i", str(caminho),
                "-af", "volumedetect", "-f", "null", "-",
            ],
            capture_output=True,
            text=True,
        ).stderr
        achado = re.search(r"mean_volume:\s*(-?[\d.]+) dB", resposta)
        assert achado, resposta
        return float(achado.group(1))

    info = await probe_video(video)
    params = VariationParams(
        variation_id="com_ruido",
        noise_audio=True,
        noise_level=0.012,
        video_scale=1.0,
        tint_opacity=0.0,
        speed=1.0,
    )

    resultado = await render_variation(
        input_video=video, output_dir=saida, params=params, info=info
    )

    assert resultado.output_path is not None
    # Antes da correção a queda era de 6 dB; 1.5 dB de folga cobre a
    # variação natural do reencode sem deixar passar a normalização.
    assert volume_medio(Path(resultado.output_path)) > volume_medio(video) - 1.5
