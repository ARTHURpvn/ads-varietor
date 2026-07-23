"""Sorteio dos parâmetros de cada variação."""

from __future__ import annotations

import random

from ads_varietor.core.metadata import MetadataGenerator
from ads_varietor.core.models import EffectSelection, FilterType, VariationParams

FILTER_CHOICES = tuple(FilterType)
# Nem toda variação com ruído ligado recebe ruído: metade fica sem, para o
# lote não ter todas as faixas de áudio parecidas.
NOISE_PROBABILITY = 0.5


class VariationGenerator:
    """Gera conjuntos de parâmetros distintos para um lote de variações.

    A seed torna os parâmetros de vídeo reprodutíveis, com uma exceção
    deliberada: o `comment` dos metadados é sempre um identificador novo.
    Se ele obedecesse à seed, rodar duas vezes com a mesma seed produziria
    arquivos idênticos — e o hash distinto é justamente o objetivo.
    """

    def __init__(self, seed: int | None = None) -> None:
        # Instância própria de Random: usar o módulo global tornaria o
        # resultado dependente de quem mais sorteou números no processo.
        self._random = random.Random(seed)
        self._metadata = MetadataGenerator(seed)

    def generate(
        self,
        count: int,
        *,
        id_prefix: str = "var",
        effects: EffectSelection | None = None,
    ) -> list[VariationParams]:
        """Gera `count` variações com identificadores únicos dentro do lote.

        `effects` limita quais famílias de efeito variam; o padrão liga todas.
        """
        if count <= 0:
            raise ValueError("A quantidade de variações precisa ser positiva.")
        selecao = effects if effects is not None else EffectSelection()
        return [
            self._generate_one(index, id_prefix, selecao) for index in range(count)
        ]

    def _generate_one(
        self, index: int, id_prefix: str, effects: EffectSelection
    ) -> VariationParams:
        metadados = self._metadata.generate()

        # Cada família só é sorteada se estiver selecionada. Desligada, o
        # parâmetro fica no valor neutro — o filtergraph pula a etapa.
        if effects.color:
            filter_type = self._random.choice(FILTER_CHOICES)
            filter_value = (
                round(self._random.uniform(0.8, 1.2), 3)
                if filter_type is not FilterType.NONE
                else 1.0
            )
            background_color = "".join(
                f"{self._random.randint(0, 255):02x}" for _ in range(3)
            )
            tint_opacity = round(self._random.uniform(0.02, 0.06), 3)
        else:
            filter_type = FilterType.NONE
            filter_value = 1.0
            background_color = "000000"
            tint_opacity = 0.0

        # Zoom discreto: o suficiente para mudar o enquadramento e os pixels,
        # pouco o bastante para não cortar nada importante.
        video_scale = (
            round(self._random.uniform(1.02, 1.08), 4) if effects.framing else 1.0
        )

        speed = (
            round(1.0 + self._random.uniform(0, 0.05), 6) if effects.speed else 1.0
        )

        noise_enabled = effects.noise and self._random.random() < NOISE_PROBABILITY

        return VariationParams(
            # O índice garante unicidade dentro do lote sem depender de
            # relógio — dois lotes no mesmo segundo colidiriam.
            variation_id=f"{id_prefix}_{index:04d}",
            metadata_title=metadados.pop("title"),
            metadata_author=metadados.pop("artist"),
            metadata_extra=metadados,
            speed=speed,
            filter_type=filter_type,
            filter_value=filter_value,
            background_color=background_color,
            video_scale=video_scale,
            tint_opacity=tint_opacity,
            noise_audio=noise_enabled,
            # Amplitude baixa de propósito: o ruído existe para alterar a
            # faixa de áudio, não para ser ouvido.
            noise_level=round(self._random.uniform(0.003, 0.012), 4)
            if noise_enabled
            else 0.0,
            # Overlay depende de um vídeo externo que o serviço não recebe,
            # então nunca é ligado pela geração automática.
            overlay_enabled=False,
            overlay_opacity=0.0,
            overlay_scale=0.3,
        )
