"""Construção do filtergraph e execução do FFmpeg para uma variação.

Todo o processamento acontece num único `-filter_complex`, e não em `-vf`.
Rótulos de stream (`[0:v]`, `[bg]`) só são válidos em filter_complex, e o
overlay do fundo colorido exige combinar duas entradas — por isso `-vf` não
serve aqui.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from video_variations.core.models import (
    FilterType,
    VariationParams,
    VariationResult,
    VariationStatus,
    VideoInfo,
)
from video_variations.core.probe import find_binary

# Margem somada à duração do ruído para cobrir arredondamento de timestamps.
NOISE_DURATION_MARGIN_SECONDS = 2.0
MINIMUM_NOISE_DURATION_SECONDS = 1.0


class FilterGraphError(ValueError):
    """Os parâmetros recebidos não produzem um filtergraph válido."""


def _to_even(value: int) -> int:
    """Arredonda para baixo até um número par.

    libx264 com pixel format yuv420p exige largura e altura pares.
    """
    return max(2, value - (value % 2))


def _apply_opacity_to_color(hex_color: str, opacity: float) -> str:
    """Escurece a cor de fundo proporcionalmente à opacidade pedida.

    Não existe nada atrás do fundo, então uma opacidade real não teria efeito
    visível. Misturar a cor com preto preserva a intenção — fundo mais fraco —
    sem um passe de composição extra.
    """
    channels = (hex_color[0:2], hex_color[2:4], hex_color[4:6])
    mixed = (int(int(channel, 16) * opacity) for channel in channels)
    return "".join(f"{value:02x}" for value in mixed)


def _build_color_filter(params: VariationParams) -> str | None:
    """Traduz o efeito de cor para a sintaxe do filtro `eq`/`hue`.

    `filter_value` chega como fator em torno de 1.0; cada filtro do FFmpeg
    tem um range próprio, daí a conversão.
    """
    if params.filter_type is FilterType.NONE:
        return None
    if params.filter_type is FilterType.BRIGHTNESS:
        # eq aceita brightness entre -1.0 e 1.0.
        return f"eq=brightness={params.filter_value - 1.0:.4f}"
    if params.filter_type is FilterType.CONTRAST:
        return f"eq=contrast={params.filter_value:.4f}"
    if params.filter_type is FilterType.SATURATE:
        return f"eq=saturation={params.filter_value:.4f}"
    if params.filter_type is FilterType.HUE:
        # hue aceita o deslocamento em graus.
        return f"hue=h={(params.filter_value - 1.0) * 180:.4f}"
    raise FilterGraphError(f"Filtro não suportado: {params.filter_type}")


def build_filter_complex(
    params: VariationParams,
    info: VideoInfo,
    *,
    has_overlay_input: bool = False,
) -> tuple[str, list[str]]:
    """Monta o filtergraph e a lista de streams a mapear na saída.

    Retorna (filtergraph, rótulos para `-map`).
    """
    canvas_width = _to_even(info.width)
    canvas_height = _to_even(info.height)
    scaled_width = _to_even(int(canvas_width * params.video_scale))
    scaled_height = _to_even(int(canvas_height * params.video_scale))
    offset_x = (canvas_width - scaled_width) // 2
    offset_y = (canvas_height - scaled_height) // 2

    background = _apply_opacity_to_color(params.background_color, params.bg_opacity)

    # --- Cadeia de vídeo -------------------------------------------------
    video_steps: list[str] = []
    color_filter = _build_color_filter(params)
    if color_filter:
        video_steps.append(color_filter)
    video_steps.append(f"scale={scaled_width}:{scaled_height}")
    video_steps.append("format=yuva420p")
    video_steps.append(f"colorchannelmixer=aa={params.video_opacity:.4f}")
    video_steps.append(f"setpts=PTS/{params.speed:.6f}")

    chains = [
        f"color=c=0x{background}:s={canvas_width}x{canvas_height}[bg]",
        f"[0:v]{','.join(video_steps)}[fg]",
        f"[bg][fg]overlay={offset_x}:{offset_y}:shortest=1[composed]",
    ]

    last_video_label = "composed"
    if has_overlay_input and params.overlay_enabled:
        overlay_width = _to_even(int(canvas_width * params.overlay_scale))
        chains.append(
            f"[1:v]scale={overlay_width}:-2,format=yuva420p,"
            f"colorchannelmixer=aa={params.overlay_opacity:.4f}[ov]"
        )
        # Sem `shortest` aqui: as duas entradas são finitas, e o clipe de
        # overlay costuma ser mais curto que o vídeo — `shortest` cortaria a
        # saída na duração do overlay. `eof_action=pass` deixa o vídeo base
        # seguir sozinho depois que o overlay acaba.
        chains.append(
            "[composed][ov]overlay=(W-w)/2:(H-h)/2:eof_action=pass"
            ":repeatlast=0[overlaid]"
        )
        last_video_label = "overlaid"

    chains.append(f"[{last_video_label}]setsar=1,format=yuv420p[vout]")
    maps = ["[vout]"]

    # --- Cadeia de áudio -------------------------------------------------
    # Sem áudio no original e sem ruído pedido, a saída fica sem faixa de
    # áudio — mapear um stream inexistente faria o FFmpeg abortar.
    audio_sources: list[str] = []
    if info.has_audio:
        chains.append(f"[0:a]atempo={params.speed:.6f}[a_original]")
        audio_sources.append("a_original")

    if params.noise_audio and params.noise_level > 0:
        # anoisesrc é uma fonte, não tem fim natural. Sem uma duração
        # explícita, um vídeo mudo com ruído renderizaria horas de áudio.
        noise_duration = max(
            MINIMUM_NOISE_DURATION_SECONDS,
            info.duration_seconds / params.speed + NOISE_DURATION_MARGIN_SECONDS,
        )
        chains.append(
            f"anoisesrc=a={params.noise_level:.4f}:d={noise_duration:.3f}"
            f":c=pink[a_noise]"
        )
        audio_sources.append("a_noise")

    if len(audio_sources) == 2:
        chains.append(
            "[a_original][a_noise]amix=inputs=2:duration=first:"
            "dropout_transition=0[aout]"
        )
        maps.append("[aout]")
    elif len(audio_sources) == 1:
        maps.append(f"[{audio_sources[0]}]")

    return ";".join(chains), maps


def build_command(
    *,
    ffmpeg_path: str,
    input_video: Path,
    output_path: Path,
    params: VariationParams,
    info: VideoInfo,
    overlay_video: Path | None = None,
) -> list[str]:
    """Monta o comando completo do FFmpeg como lista de argumentos.

    Sempre lista, nunca string: o comando é executado sem shell, então nada
    vindo do usuário pode ser interpretado como sintaxe de shell.
    """
    has_overlay = overlay_video is not None and params.overlay_enabled
    filter_complex, maps = build_filter_complex(
        params, info, has_overlay_input=has_overlay
    )

    command = [
        ffmpeg_path,
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-i",
        str(input_video),
    ]
    if has_overlay and overlay_video is not None:
        command.extend(["-i", str(overlay_video)])

    command.extend(["-filter_complex", filter_complex])
    for label in maps:
        command.extend(["-map", label])

    if params.metadata_title:
        command.extend(["-metadata", f"title={params.metadata_title}"])
    if params.metadata_author:
        command.extend(["-metadata", f"artist={params.metadata_author}"])

    command.extend(["-c:v", "libx264", "-preset", "ultrafast", "-crf", "23"])
    if len(maps) > 1:
        command.extend(["-c:a", "aac", "-b:a", "128k"])
        # Garante que a saída termine com o vídeo, mesmo que a faixa de
        # áudio gerada seja ligeiramente mais longa.
        command.append("-shortest")
    command.append(str(output_path))
    return command


async def render_variation(
    *,
    input_video: Path,
    output_dir: Path,
    params: VariationParams,
    info: VideoInfo,
    overlay_video: Path | None = None,
    timeout_seconds: int = 300,
) -> VariationResult:
    """Renderiza uma variação e devolve o resultado.

    Nunca levanta exceção por falha do FFmpeg: a falha vira um
    VariationResult com status FAILED, para que uma variação ruim não
    derrube o batch inteiro.
    """
    output_path = output_dir / f"{params.variation_id}.mp4"
    command = build_command(
        ffmpeg_path=find_binary("ffmpeg"),
        input_video=input_video,
        output_path=output_path,
        params=params,
        info=info,
        overlay_video=overlay_video,
    )

    loop = asyncio.get_running_loop()
    started_at = loop.time()
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        _, stderr = await asyncio.wait_for(
            process.communicate(), timeout=timeout_seconds
        )
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        # O FFmpeg deixa um .mp4 truncado ao ser morto no meio do encode.
        # Manter esse arquivo faria o download em lote entregar um vídeo
        # corrompido junto com os bons.
        output_path.unlink(missing_ok=True)
        return VariationResult(
            variation_id=params.variation_id,
            status=VariationStatus.FAILED,
            error=f"Tempo de processamento excedido ({timeout_seconds}s).",
        )
    except asyncio.CancelledError:
        # Cancelamento do job precisa matar o processo filho, senão o
        # FFmpeg continua consumindo CPU depois do DELETE.
        process.terminate()
        await process.wait()
        output_path.unlink(missing_ok=True)
        raise

    elapsed = loop.time() - started_at

    if process.returncode != 0 or not output_path.exists():
        message = stderr.decode("utf-8", errors="replace").strip()
        last_line = message.splitlines()[-1] if message else "erro desconhecido"
        output_path.unlink(missing_ok=True)
        return VariationResult(
            variation_id=params.variation_id,
            status=VariationStatus.FAILED,
            error=f"Falha ao renderizar: {last_line[:300]}",
            duration_seconds=elapsed,
        )

    return VariationResult(
        variation_id=params.variation_id,
        status=VariationStatus.COMPLETED,
        output_path=str(output_path),
        size_bytes=output_path.stat().st_size,
        duration_seconds=elapsed,
    )
