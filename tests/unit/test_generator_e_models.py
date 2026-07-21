"""Testes do motor de sorteio de variações e dos modelos de domínio."""

from __future__ import annotations

import random

import pytest
from pydantic import ValidationError

from video_variations.core.generator import VariationGenerator
from video_variations.core.models import (
    VARIATION_ID_PATTERN,
    FilterType,
    VariationParams,
)


# ---------------------------------------------------------------------------
# VariationGenerator.generate — contagem e unicidade
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("count", [1, 2, 5, 50])
def test_devolve_exatamente_n_variacoes_quando_count_positivo(count: int) -> None:
    variacoes = VariationGenerator(seed=1).generate(count)

    assert len(variacoes) == count


def test_ids_sao_unicos_quando_lote_grande_gerado_de_uma_vez() -> None:
    """Regressão: os ids vinham do relógio em segundos e colidiam."""
    variacoes = VariationGenerator(seed=7).generate(300)

    ids = [variacao.variation_id for variacao in variacoes]

    assert len(set(ids)) == 300


def test_ids_sao_unicos_quando_lotes_gerados_no_mesmo_instante() -> None:
    """Dois lotes com prefixos distintos não podem colidir entre si."""
    gerador = VariationGenerator(seed=7)

    lote_a = gerador.generate(20, id_prefix="lote_a")
    lote_b = gerador.generate(20, id_prefix="lote_b")

    ids = [v.variation_id for v in lote_a] + [v.variation_id for v in lote_b]

    assert len(set(ids)) == 40


def test_ids_batem_com_o_padrao_aceito_pelo_modelo_quando_gerados() -> None:
    variacoes = VariationGenerator(seed=3).generate(100)

    for variacao in variacoes:
        assert VARIATION_ID_PATTERN.match(variacao.variation_id), variacao.variation_id
        # Reconstruir o modelo prova que o id é aceito pelo validador.
        VariationParams(variation_id=variacao.variation_id)


def test_id_usa_o_prefixo_informado_quando_id_prefix_customizado() -> None:
    variacoes = VariationGenerator(seed=3).generate(3, id_prefix="job_abc")

    assert all(v.variation_id.startswith("job_abc_") for v in variacoes)


# ---------------------------------------------------------------------------
# Determinismo
# ---------------------------------------------------------------------------


def _sem_comment(variacoes: list) -> list[dict]:
    """Serializa ignorando o `comment`, que é único por construção.

    O `comment` carrega o identificador que garante hash distinto entre
    arquivos; ele não obedece à seed de propósito.
    """
    saida = []
    for variacao in variacoes:
        dados = variacao.model_dump()
        dados["metadata_extra"] = {
            chave: valor
            for chave, valor in dados["metadata_extra"].items()
            if chave != "comment"
        }
        saida.append(dados)
    return saida


def test_resultado_identico_quando_mesma_seed() -> None:
    primeiro = VariationGenerator(seed=42).generate(25)
    segundo = VariationGenerator(seed=42).generate(25)

    assert _sem_comment(primeiro) == _sem_comment(segundo)


def test_comment_e_sempre_novo_mesmo_quando_a_seed_se_repete() -> None:
    """O identificador do comment é o que garante hash distinto.

    Se ele obedecesse à seed, dois lotes com a mesma seed gerariam arquivos
    byte a byte iguais — exatamente o que o sistema existe para evitar.
    """
    primeiro = VariationGenerator(seed=42).generate(10)
    segundo = VariationGenerator(seed=42).generate(10)

    comentarios = [v.metadata_extra["comment"] for v in primeiro] + [
        v.metadata_extra["comment"] for v in segundo
    ]

    assert len(set(comentarios)) == 20


def test_resultado_diferente_quando_seeds_diferentes() -> None:
    primeiro = VariationGenerator(seed=42).generate(25)
    segundo = VariationGenerator(seed=43).generate(25)

    assert [v.model_dump() for v in primeiro] != [v.model_dump() for v in segundo]


def test_resultado_nao_muda_quando_modulo_random_global_e_mexido() -> None:
    """O gerador precisa usar Random próprio, não o estado global do módulo."""
    random.seed(999)
    esperado = VariationGenerator(seed=42).generate(20)

    random.seed(1)
    [random.random() for _ in range(500)]
    obtido = VariationGenerator(seed=42).generate(20)

    assert _sem_comment(obtido) == _sem_comment(esperado)


def test_gerador_produz_lotes_diferentes_quando_as_seeds_sao_diferentes() -> None:
    """Seeds explícitas: o resultado é determinístico e a diferença entre os
    dois lotes prova que a seed realmente alimenta o sorteio.
    """
    primeiro = VariationGenerator(seed=1).generate(30)
    segundo = VariationGenerator(seed=2).generate(30)

    assert [v.model_dump() for v in primeiro] != [v.model_dump() for v in segundo]


# ---------------------------------------------------------------------------
# Limites de todos os parâmetros sorteados
# ---------------------------------------------------------------------------


def test_todos_os_parametros_ficam_dentro_dos_limites_quando_200_variacoes() -> None:
    variacoes = VariationGenerator(seed=2024).generate(200)

    assert len(variacoes) == 200
    for variacao in variacoes:
        # Revalida o objeto inteiro contra o modelo: qualquer campo fora dos
        # limites declarados vira ValidationError aqui.
        VariationParams.model_validate(variacao.model_dump())

        assert 0.5 <= variacao.speed <= 2.0
        assert 0.0 <= variacao.filter_value <= 2.0
        assert isinstance(variacao.filter_type, FilterType)
        assert VARIATION_ID_PATTERN.match(variacao.variation_id)
        assert len(variacao.background_color) == 6
        assert int(variacao.background_color, 16) >= 0
        assert 0.0 <= variacao.tint_opacity <= 0.2
        # A escala nunca desce abaixo de 1: o vídeo é ampliado e cortado,
        # nunca reduzido, para não deixar faixa de fundo aparecendo.
        assert 1.0 <= variacao.video_scale <= 1.5
        assert 0.0 <= variacao.noise_level <= 1.0
        assert 0.0 <= variacao.overlay_opacity <= 1.0
        assert 0.05 <= variacao.overlay_scale <= 1.0


def test_ruido_zerado_quando_noise_audio_desligado() -> None:
    variacoes = VariationGenerator(seed=11).generate(200)

    for variacao in variacoes:
        if not variacao.noise_audio:
            assert variacao.noise_level == 0.0
        if not variacao.overlay_enabled:
            assert variacao.overlay_opacity == 0.0


def test_filtro_neutro_quando_filter_type_none() -> None:
    variacoes = VariationGenerator(seed=13).generate(200)

    for variacao in variacoes:
        if variacao.filter_type is FilterType.NONE:
            assert variacao.filter_value == 1.0


# ---------------------------------------------------------------------------
# Entradas inválidas em generate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("count", [0, -1, -100])
def test_levanta_value_error_quando_count_nao_positivo(count: int) -> None:
    with pytest.raises(ValueError):
        VariationGenerator(seed=1).generate(count)


# ---------------------------------------------------------------------------
# VariationParams — validação
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "variation_id",
    [
        "var/0001",
        "../etc/passwd",
        "var.0001",
        "arquivo.mp4",
        "",
        "a" * 65,
        "VAR_0001",
        "var 0001",
        "var-0001",
    ],
)
def test_rejeita_variation_id_quando_fora_do_padrao(variation_id: str) -> None:
    with pytest.raises(ValidationError):
        VariationParams(variation_id=variation_id)


@pytest.mark.parametrize("variation_id", ["a", "var_0001", "x" * 64, "0", "abc123"])
def test_aceita_variation_id_quando_dentro_do_padrao(variation_id: str) -> None:
    assert VariationParams(variation_id=variation_id).variation_id == variation_id


@pytest.mark.parametrize(
    "background_color",
    ["fff", "1234567", "gggggg", "#ffffff", "", "12345", "ff ffff"],
)
def test_rejeita_background_color_quando_nao_for_hex_de_6(
    background_color: str,
) -> None:
    with pytest.raises(ValidationError):
        VariationParams(variation_id="var_0001", background_color=background_color)


@pytest.mark.parametrize("background_color", ["000000", "ffffff", "AbC123"])
def test_aceita_background_color_quando_hex_de_6(background_color: str) -> None:
    params = VariationParams(
        variation_id="var_0001", background_color=background_color
    )

    assert params.background_color == background_color


@pytest.mark.parametrize("speed", [0.49, 0.0, -1.0, 2.01, 10.0])
def test_rejeita_speed_quando_fora_de_0_5_a_2_0(speed: float) -> None:
    with pytest.raises(ValidationError):
        VariationParams(variation_id="var_0001", speed=speed)


@pytest.mark.parametrize("speed", [0.5, 1.0, 2.0])
def test_aceita_speed_quando_no_limite(speed: float) -> None:
    assert VariationParams(variation_id="var_0001", speed=speed).speed == speed


@pytest.mark.parametrize("video_scale", [0.99, 0.5, 0.0, -0.5, 1.51, 3.0])
def test_rejeita_video_scale_quando_fora_de_1_0_a_1_5(video_scale: float) -> None:
    with pytest.raises(ValidationError):
        VariationParams(variation_id="var_0001", video_scale=video_scale)


@pytest.mark.parametrize("video_scale", [1.0, 1.05, 1.5])
def test_aceita_video_scale_quando_no_limite(video_scale: float) -> None:
    params = VariationParams(variation_id="var_0001", video_scale=video_scale)

    assert params.video_scale == video_scale


def test_variation_id_e_obrigatorio_quando_nao_informado() -> None:
    with pytest.raises(ValidationError):
        VariationParams()


# ---------------------------------------------------------------------------
# Imutabilidade
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("variation_id", "outro_id"),
        ("speed", 1.5),
        ("background_color", "ffffff"),
        ("noise_audio", True),
    ],
)
def test_variation_params_e_imutavel_quando_tenta_atribuir_campo(
    campo: str, valor: object
) -> None:
    params = VariationParams(variation_id="var_0001")

    with pytest.raises(ValidationError):
        setattr(params, campo, valor)

    assert VariationParams(variation_id="var_0001") == params
