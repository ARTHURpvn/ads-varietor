"""Geração de metadados variados para cada saída.

Metadados fixos são uma assinatura: um lote inteiro saindo com o mesmo
`title` e o mesmo `encoder` é tão identificável quanto o arquivo original.
Aqui cada variação recebe um conjunto próprio, com valores plausíveis de
câmera e editor comuns.
"""

from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta, timezone

MODELOS = (
    "iPhone 14 Pro",
    "iPhone 15",
    "Pixel 8",
    "Galaxy S23",
    "Canon EOS R6",
    "SM-A546E",
)

GENEROS = ("Entretenimento", "Educação", "Estilo de vida", "Notícias", "Esporte")


class MetadataGenerator:
    """Sorteia um conjunto de metadados por variação."""

    def __init__(self, seed: int | None = None) -> None:
        self._random = random.Random(seed)

    def generate(self, *, agora: datetime | None = None) -> dict[str, str]:
        """Devolve os pares chave/valor de metadados de uma variação.

        O `comment` carrega um UUID: é ele que garante que dois arquivos com
        exatamente os mesmos parâmetros de vídeo ainda saiam com hashes
        diferentes.
        """
        referencia = agora if agora is not None else datetime.now(timezone.utc)
        # Data de criação recuada de forma aleatória, para que o lote não
        # tenha todos os arquivos com o mesmo instante.
        criacao = referencia - timedelta(
            days=self._random.randint(0, 240),
            hours=self._random.randint(0, 23),
            minutes=self._random.randint(0, 59),
            seconds=self._random.randint(0, 59),
        )

        # Só entram tags que o contêiner MP4 realmente preserva. `make`,
        # `model`, `software` e `encoder` são descartados pelo muxer — pedi-los
        # daria a falsa impressão de que estão sendo gravados.
        return {
            "title": self._titulo(),
            "artist": self._autor(),
            "comment": uuid.uuid4().hex,
            "creation_time": criacao.strftime("%Y-%m-%dT%H:%M:%S.000000Z"),
            "date": criacao.strftime("%Y-%m-%d"),
            "genre": self._random.choice(GENEROS),
        }

    def _titulo(self) -> str:
        prefixos = ("VID", "MOV", "REC", "clip", "video")
        return (
            f"{self._random.choice(prefixos)}_"
            f"{self._random.randint(10_000_000, 99_999_999)}"
        )

    def _autor(self) -> str:
        return self._random.choice(MODELOS)
