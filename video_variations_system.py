#!/usr/bin/env python3
"""
Video Variations System
Gera múltiplas variações de um vídeo com parâmetros que variam automaticamente.
"""

import os
import json
import random
import subprocess
import tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Tuple
from dataclasses import dataclass, asdict
import argparse
import time
from datetime import datetime


@dataclass
class VideoVariationConfig:
    """Configuração de uma variação de vídeo"""
    variation_id: str

    # Metadados
    metadata_title: str = None
    metadata_author: str = None

    # Velocidade
    speed: float = 1.0  # 1.0 a 1.05, com valores não-exatos
    filter_type: str = "none"  # none, brightness, contrast, saturate, hue
    filter_value: float = 1.0

    # Fundo e escala
    background_color: str = "000000"  # RGB hex
    bg_opacity: float = 1.0
    video_opacity: float = 0.8  # Transparência do vídeo original
    video_scale: float = 0.9  # Escala do vídeo (0.8 a 1.0)

    # Áudio de ruído
    noise_audio: bool = False
    noise_level: float = 0.05  # 0.0 a 0.1

    # Overlay de vídeo
    overlay_enabled: bool = False
    overlay_opacity: float = 0.1
    overlay_scale: float = 0.3


class VideoVariationGenerator:
    """Gera configurações de variações com parâmetros variados"""

    def __init__(self, seed: int = None):
        if seed is not None:
            random.seed(seed)

    def generate_variations(self, count: int = 5) -> List[VideoVariationConfig]:
        """Gera N variações com parâmetros aleatórios"""
        variations = []

        for i in range(count):
            # Speed: 1.0 a 1.05 com valores não-exatos
            speed = round(1.0 + random.uniform(0, 0.05), 6)

            # Filtros disponíveis
            filters = ["none", "brightness", "contrast", "saturate", "hue"]
            filter_type = random.choice(filters)
            filter_value = round(random.uniform(0.8, 1.2), 3) if filter_type != "none" else 1.0

            # Background
            bg_color = f"{random.randint(0, 255):02x}{random.randint(0, 255):02x}{random.randint(0, 255):02x}"
            bg_opacity = round(random.uniform(0.6, 1.0), 2)

            # Vídeo
            video_opacity = round(random.uniform(0.7, 0.95), 2)
            video_scale = round(random.uniform(0.8, 1.0), 2)

            # Ruído (50% de chance)
            noise_enabled = random.choice([True, False])
            noise_level = round(random.uniform(0.02, 0.08), 3) if noise_enabled else 0

            # Overlay (30% de chance)
            overlay_enabled = random.random() < 0.3
            overlay_opacity = round(random.uniform(0.05, 0.15), 2) if overlay_enabled else 0
            overlay_scale = round(random.uniform(0.2, 0.4), 2) if overlay_enabled else 0

            config = VideoVariationConfig(
                variation_id=f"var_{i:03d}_{datetime.now().strftime('%s')}",
                metadata_title=f"Video Variation {i}",
                metadata_author="Auto Generated",
                speed=speed,
                filter_type=filter_type,
                filter_value=filter_value,
                background_color=bg_color,
                bg_opacity=bg_opacity,
                video_opacity=video_opacity,
                video_scale=video_scale,
                noise_audio=noise_enabled,
                noise_level=noise_level,
                overlay_enabled=overlay_enabled,
                overlay_opacity=overlay_opacity,
                overlay_scale=overlay_scale
            )
            variations.append(config)

        return variations


class VideoProcessor:
    """Processa vídeos com FFmpeg aplicando variações"""

    def __init__(self, temp_dir: str = None):
        self.temp_dir = temp_dir or tempfile.gettempdir()
        self.ffmpeg_path = self._find_ffmpeg()

    def _find_ffmpeg(self) -> str:
        """Encontra o FFmpeg no sistema"""
        try:
            result = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
            if result.returncode == 0:
                return "ffmpeg"
        except:
            pass

        # Tenta caminhos comuns
        for path in ["/usr/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/opt/homebrew/bin/ffmpeg"]:
            if os.path.exists(path):
                return path

        raise RuntimeError("FFmpeg não encontrado. Instale com: brew install ffmpeg (Mac) ou apt install ffmpeg (Linux)")

    def process_variation(self,
                         input_video: str,
                         output_dir: str,
                         config: VideoVariationConfig,
                         overlay_video: str = None) -> Tuple[bool, str]:
        """
        Processa uma variação de vídeo
        Retorna: (sucesso, caminho_output ou mensagem_erro)
        """
        try:
            output_path = os.path.join(output_dir, f"{config.variation_id}.mp4")

            # Construir filtro FFmpeg complexo
            filter_chain = self._build_filter_chain(config, overlay_video is not None)

            # Comando FFmpeg base
            cmd = [self.ffmpeg_path]
            cmd.extend(["-i", input_video])

            # Adiciona vídeo overlay se fornecido
            if overlay_video and config.overlay_enabled:
                cmd.extend(["-i", overlay_video])

            # Adiciona filtro
            if filter_chain:
                cmd.extend(["-vf", filter_chain])

            # Velocidade (usando setpts)
            if config.speed != 1.0:
                cmd.extend(["-itsscale", str(1.0 / config.speed)])

            # Áudio: adiciona ruído se configurado
            if config.noise_audio:
                # Gera ruído com FFmpeg
                cmd.extend(["-af", f"anoisesrc=a={config.noise_level}:d=0.001[noise]"])
                # Mistura com áudio original (se houver)
                # Este é um exemplo simplificado

            # Metadados
            if config.metadata_title:
                cmd.extend(["-metadata", f"title={config.metadata_title}"])
            if config.metadata_author:
                cmd.extend(["-metadata", f"author={config.metadata_author}"])

            # Output
            cmd.extend(["-c:v", "libx264", "-preset", "ultrafast", "-crf", "23"])
            cmd.extend(["-c:a", "aac", "-b:a", "128k"])
            cmd.append(output_path)
            cmd.extend(["-y"])  # Overwrite

            # Log
            print(f"[{config.variation_id}] Iniciando processamento...")
            print(f"  Speed: {config.speed}, Filter: {config.filter_type}, Noise: {config.noise_audio}")

            # Executa
            start_time = time.time()
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120  # 2 minutos timeout
            )
            elapsed = time.time() - start_time

            if result.returncode == 0:
                file_size = os.path.getsize(output_path) / (1024 * 1024)  # MB
                print(f"[{config.variation_id}] ✓ Concluído em {elapsed:.1f}s ({file_size:.1f}MB)")
                return True, output_path
            else:
                error = result.stderr[-500:] if result.stderr else "Erro desconhecido"
                print(f"[{config.variation_id}] ✗ Erro: {error}")
                return False, error

        except subprocess.TimeoutExpired:
            return False, "Timeout (> 2 minutos)"
        except Exception as e:
            return False, str(e)

    def _build_filter_chain(self, config: VideoVariationConfig, has_overlay: bool = False) -> str:
        """Constrói o filtro FFmpeg complexo"""
        filters = []

        # 1. Aplicar filtro de cor/efeito
        if config.filter_type != "none":
            if config.filter_type == "brightness":
                filters.append(f"eq=brightness={config.filter_value}:1")
            elif config.filter_type == "contrast":
                filters.append(f"eq=contrast={config.filter_value}")
            elif config.filter_type == "saturate":
                filters.append(f"hue=s={config.filter_value}")
            elif config.filter_type == "hue":
                filters.append(f"hue=h={config.filter_value * 180}:s=1")

        # 2. Redimensionar vídeo
        scale_factor = config.video_scale
        filters.append(f"scale=iw*{scale_factor}:ih*{scale_factor}:force_original_aspect_ratio=decrease")

        # 3. Pad com background (criar fundo)
        bg_color = f"#{config.background_color}"
        filters.append(f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color={bg_color}")

        # 4. Aplicar transparência ao vídeo
        filters.append(f"format=yuva420p,eval=frame")

        # 5. Overlay se existe
        if has_overlay:
            filters.append(f"[0:v][1:v]overlay=(W-w)/2:(H-h)/2:alpha={config.overlay_opacity}")

        return ",".join(filters) if filters else None


class VariationProcessor:
    """Orquestra o processamento de múltiplas variações em paralelo"""

    def __init__(self, max_workers: int = 4):
        self.generator = VideoVariationGenerator()
        self.processor = VideoProcessor()
        self.max_workers = max_workers

    def process_batch(self,
                     input_video: str,
                     output_dir: str,
                     num_variations: int = 5,
                     overlay_video: str = None) -> Dict:
        """Processa múltiplas variações em paralelo"""

        # Valida entrada
        if not os.path.exists(input_video):
            return {"success": False, "error": f"Vídeo não encontrado: {input_video}"}

        os.makedirs(output_dir, exist_ok=True)

        # Gera configurações
        print(f"\n📝 Gerando {num_variations} variações...")
        configs = self.generator.generate_variations(num_variations)

        # Exibe preview das configurações
        print("\n⚙️  Configurações geradas:")
        for cfg in configs[:3]:  # Mostra as 3 primeiras
            print(f"  {cfg.variation_id}: speed={cfg.speed}, filter={cfg.filter_type}, "
                  f"bg=#{cfg.background_color}, noise={cfg.noise_audio}")
        if len(configs) > 3:
            print(f"  ... e mais {len(configs) - 3}")

        # Processa em paralelo
        print(f"\n⚡ Processando {num_variations} variações (max {self.max_workers} paralelas)...")
        print("=" * 60)

        results = {"success": [], "failed": []}
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(
                    self.processor.process_variation,
                    input_video,
                    output_dir,
                    config,
                    overlay_video
                ): config for config in configs
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

        # Salva relatório
        results["summary"] = {
            "total": num_variations,
            "success": len(results["success"]),
            "failed": len(results["failed"]),
            "total_time_seconds": elapsed,
            "avg_time_per_video": elapsed / num_variations,
            "output_directory": output_dir
        }

        return results


def main():
    parser = argparse.ArgumentParser(description="Gera múltiplas variações de um vídeo")
    parser.add_argument("input_video", help="Caminho do vídeo de entrada")
    parser.add_argument("-o", "--output", default="./output", help="Diretório de saída")
    parser.add_argument("-n", "--num-variations", type=int, default=5, help="Número de variações (padrão: 5)")
    parser.add_argument("-w", "--workers", type=int, default=4, help="Número de processadores paralelos (padrão: 4)")
    parser.add_argument("--overlay-video", help="Vídeo para overlay (opcional)")
    parser.add_argument("--save-config", action="store_true", help="Salva as configurações em JSON")

    args = parser.parse_args()

    # Executa
    processor = VariationProcessor(max_workers=args.workers)
    results = processor.process_batch(
        args.input_video,
        args.output,
        args.num_variations,
        args.overlay_video
    )

    # Salva relatório
    report_path = os.path.join(args.output, "report.json")
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n📄 Relatório salvo em: {report_path}")

    # Salva configurações se solicitado
    if args.save_config:
        config_path = os.path.join(args.output, "configurations.json")
        with open(config_path, "w") as f:
            json.dump(
                [asdict(cfg) for cfg in results.get("success", [])],
                f,
                indent=2
            )
        print(f"⚙️  Configurações salvas em: {config_path}")


if __name__ == "__main__":
    main()
