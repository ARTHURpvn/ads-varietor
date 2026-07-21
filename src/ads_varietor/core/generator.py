"""Sorteio dos parâmetros de cada variação."""

from __future__ import annotations

import random

from ads_varietor.core.metadata import MetadataGenerator
from ads_varietor.core.models import FilterType, VariationParams

FILTER_CHOICES = tuple(FilterType)
NOISE_PROBABILITY = 0.5
OVERLAY_PROBABILITY = 0.3


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

    def generate(self, count: int, *, id_prefix: str = "var") -> list[VariationParams]:
        """Gera `count` variações com identificadores únicos dentro do lote."""
        if count <= 0:
            raise ValueError("A quantidade de variações precisa ser positiva.")
        return [self._generate_one(index, id_prefix) for index in range(count)]

    def _generate_one(self, index: int, id_prefix: str) -> VariationParams:
        metadados = self._metadata.generate()
        filter_type = self._random.choice(FILTER_CHOICES)
        filter_value = (
            round(self._random.uniform(0.8, 1.2), 3)
            if filter_type is not FilterType.NONE
            else 1.0
        )

        noise_enabled = self._random.random() < NOISE_PROBABILITY
        overlay_enabled = self._random.random() < OVERLAY_PROBABILITY

        return VariationParams(
            # O índice garante unicidade dentro do lote sem depender de
            # relógio — dois lotes no mesmo segundo colidiriam.
            variation_id=f"{id_prefix}_{index:04d}",
            metadata_title=metadados.pop("title"),
            metadata_author=metadados.pop("artist"),
            metadata_extra=metadados,
            speed=round(1.0 + self._random.uniform(0, 0.05), 6),
            filter_type=filter_type,
            filter_value=filter_value,
            background_color="".join(
                f"{self._random.randint(0, 255):02x}" for _ in range(3)
            ),
            # Zoom discreto: o suficiente para mudar o enquadramento e os
            # pixels, pouco o bastante para não cortar nada importante.
            video_scale=round(self._random.uniform(1.02, 1.08), 4),
            tint_opacity=round(self._random.uniform(0.02, 0.06), 3),
            noise_audio=noise_enabled,
            # Amplitude baixa de propósito: o ruído existe para alterar a
            # faixa de áudio, não para ser ouvido.
            noise_level=round(self._random.uniform(0.003, 0.012), 4)
            if noise_enabled
            else 0.0,
            overlay_enabled=overlay_enabled,
            overlay_opacity=round(self._random.uniform(0.05, 0.15), 2)
            if overlay_enabled
            else 0.0,
            overlay_scale=round(self._random.uniform(0.2, 0.4), 2),
        )
