"""Interface de linha de comando do gerador de variações."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from video_variations.core.batch import render_batch, summarize
from video_variations.core.generator import VariationGenerator
from video_variations.core.models import VariationParams
from video_variations.core.probe import FFmpegNotFoundError, InvalidVideoError


def _load_variations_from_config(config_path: Path) -> list[VariationParams]:
    """Lê parâmetros fixos de um JSON no formato `{"variations": [...]}`."""
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    entries = payload.get("variations", [])
    if not entries:
        raise ValueError("O arquivo de configuração não contém variações.")
    return [VariationParams.model_validate(entry) for entry in entries]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="video-variations",
        description="Gera múltiplas variações de um vídeo.",
    )
    parser.add_argument("input_video", type=Path, help="Caminho do vídeo de entrada")
    parser.add_argument(
        "-o", "--output", type=Path, default=Path("./output"),
        help="Diretório de saída (padrão: ./output)",
    )
    parser.add_argument(
        "-n", "--num-variations", type=int, default=5,
        help="Número de variações a gerar (padrão: 5)",
    )
    parser.add_argument(
        "-w", "--workers", type=int, default=4,
        help="Quantos FFmpeg rodam em paralelo (padrão: 4)",
    )
    parser.add_argument(
        "-c", "--config", type=Path,
        help="JSON com parâmetros fixos, em vez de sorteá-los",
    )
    parser.add_argument("--overlay-video", type=Path, help="Vídeo de overlay opcional")
    parser.add_argument("--seed", type=int, help="Semente para sorteio reproduzível")
    parser.add_argument(
        "--save-config", action="store_true",
        help="Salva os parâmetros usados em configurations.json",
    )
    return parser


async def _run(args: argparse.Namespace) -> int:
    if not args.input_video.is_file():
        print(f"Vídeo não encontrado: {args.input_video}", file=sys.stderr)
        return 1

    if args.config is not None:
        if not args.config.is_file():
            print(f"Configuração não encontrada: {args.config}", file=sys.stderr)
            return 1
        variations = _load_variations_from_config(args.config)
    else:
        variations = VariationGenerator(seed=args.seed).generate(args.num_variations)

    print(f"Gerando {len(variations)} variações de {args.input_video.name}...")

    results = await render_batch(
        input_video=args.input_video,
        output_dir=args.output,
        variations=variations,
        overlay_video=args.overlay_video,
        max_concurrent=args.workers,
    )

    stats = summarize(results)
    for result in results:
        marker = "ok " if result.error is None else "erro"
        detail = result.error or f"{(result.size_bytes or 0) / 1_048_576:.1f} MB"
        print(f"  [{marker}] {result.variation_id}: {detail}")

    print(f"\n{stats['completed']} concluídas, {stats['failed']} com erro.")

    args.output.mkdir(parents=True, exist_ok=True)
    report_path = args.output / "report.json"
    report_path.write_text(
        json.dumps(
            {
                "summary": stats,
                "results": [result.model_dump() for result in results],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"Relatório: {report_path}")

    if args.save_config:
        config_path = args.output / "configurations.json"
        config_path.write_text(
            json.dumps(
                {"variations": [item.model_dump(mode="json") for item in variations]},
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        print(f"Parâmetros: {config_path}")

    return 0 if stats["failed"] == 0 else 1


def main() -> int:
    args = _build_parser().parse_args()
    try:
        return asyncio.run(_run(args))
    except FFmpegNotFoundError as error:
        print(str(error), file=sys.stderr)
        return 2
    except (InvalidVideoError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrompido.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
