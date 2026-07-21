#!/usr/bin/env python3
"""
Video Variations from Config
Processa variações usando configurações de um arquivo JSON
"""

import json
import os
import argparse
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict

# Importa do módulo principal
from video_variations_system import VideoVariationConfig, VideoProcessor


class ConfigBasedVariationProcessor:
    """Processa variações baseado em arquivo de configuração JSON"""

    def __init__(self, config_path: str):
        self.config_path = config_path
        self.processor = VideoProcessor()
        self.configs = self._load_config()

    def _load_config(self) -> list:
        """Carrega configurações do JSON"""
        with open(self.config_path, 'r') as f:
            data = json.load(f)

        configs = []
        if "variations" in data:
            for var in data["variations"]:
                config = VideoVariationConfig(**var)
                configs.append(config)

        print(f"✅ Carregadas {len(configs)} configurações de {self.config_path}")
        return configs

    def process_batch(self,
                     input_video: str,
                     output_dir: str,
                     overlay_video: str = None,
                     max_workers: int = 4) -> dict:
        """Processa variações com configurações fixas"""

        if not os.path.exists(input_video):
            return {"success": False, "error": f"Vídeo não encontrado: {input_video}"}

        os.makedirs(output_dir, exist_ok=True)

        print(f"\n⚡ Processando {len(self.configs)} variações (max {max_workers} paralelas)...")
        print("=" * 60)

        results = {"success": [], "failed": []}
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    self.processor.process_variation,
                    input_video,
                    output_dir,
                    config,
                    overlay_video
                ): config for config in self.configs
            }

            for future in as_completed(futures):
                config = futures[future]
                success, result = future.result()

                if success:
                    results["success"].append({
                        "variation_id": config.variation_id,
                        "output": result,
                        "config": asdict(config)
                    })
                else:
                    results["failed"].append({
                        "variation_id": config.variation_id,
                        "error": result
                    })

        elapsed = time.time() - start_time

        print("=" * 60)
        print(f"\n✅ Concluído em {elapsed:.1f}s")
        print(f"   ✓ {len(results['success'])} sucesso")
        print(f"   ✗ {len(results['failed'])} erro")

        results["summary"] = {
            "total": len(self.configs),
            "success": len(results["success"]),
            "failed": len(results["failed"]),
            "total_time_seconds": elapsed,
            "avg_time_per_video": elapsed / len(self.configs) if self.configs else 0,
            "output_directory": output_dir
        }

        return results


def main():
    parser = argparse.ArgumentParser(
        description="Processa variações de vídeo usando configuração JSON"
    )
    parser.add_argument(
        "input_video",
        help="Caminho do vídeo de entrada"
    )
    parser.add_argument(
        "-c", "--config",
        required=True,
        help="Arquivo JSON com configurações das variações"
    )
    parser.add_argument(
        "-o", "--output",
        default="./output",
        help="Diretório de saída (padrão: ./output)"
    )
    parser.add_argument(
        "-w", "--workers",
        type=int,
        default=4,
        help="Número de processadores paralelos (padrão: 4)"
    )
    parser.add_argument(
        "--overlay-video",
        help="Vídeo para overlay (opcional)"
    )

    args = parser.parse_args()

    # Valida arquivo de config
    if not os.path.exists(args.config):
        print(f"❌ Arquivo não encontrado: {args.config}")
        return

    # Executa
    processor = ConfigBasedVariationProcessor(args.config)
    results = processor.process_batch(
        args.input_video,
        args.output,
        args.overlay_video,
        args.workers
    )

    # Salva relatório
    report_path = os.path.join(args.output, "report_from_config.json")
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n📄 Relatório salvo em: {report_path}")


if __name__ == "__main__":
    main()
