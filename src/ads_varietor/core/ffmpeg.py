"""Construção do filtergraph e execução do FFmpeg para uma variação.

Todo o processamento acontece num único `-filter_complex`, e não em `-vf`.
Rótulos de stream (`[0:v]`, `[bg]`) só são válidos em filter_complex, e o
overlay do fundo colorido exige combinar duas entradas — por isso `-vf` não
serve aqui.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from pathlib import Path

from ads_varietor.core.models import (
    FilterType,
    ProcessingMode,
    VariationParams,
    VariationResult,
    VariationStatus,
    VideoInfo,
)
from ads_varietor.core.probe import find_binary

# Margem somada à duração do ruído para cobrir arredondamento de timestamps.
NOISE_DURATION_MARGIN_SECONDS = 2.0
MINIMUM_NOISE_DURATION_SECONDS = 1.0
# Peso do ruído na mixagem. Junto com a amplitude sorteada, deixa o ruído
# por volta de -75 dB, contra -21 dB de um áudio comum: altera a faixa de
# áudio sem que se ouça chiado.
NOISE_MIX_WEIGHT = 0.15

logger = logging.getLogger(__name__)


class FilterGraphError(ValueError):
    """Os parâmetros recebidos não produzem um filtergraph válido."""


def _to_even(value: int) -> int:
    """Arredonda para baixo até um número par.

    libx264 com pixel format yuv420p exige largura e altura pares.
    """
    return max(2, value - (value % 2))


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
    # A escala é sempre acima de 1: o vídeo cresce e o excedente é cortado
    # nas bordas. Assim a saída mantém a resolução do original sem faixas de
    # fundo aparecendo — o enquadramento muda, o formato não.
    scaled_width = _to_even(int(canvas_width * params.video_scale))
    scaled_height = _to_even(int(canvas_height * params.video_scale))

    # --- Cadeia de vídeo -------------------------------------------------
    video_steps: list[str] = []
    color_filter = _build_color_filter(params)
    if color_filter:
        video_steps.append(color_filter)
    video_steps.append(f"scale={scaled_width}:{scaled_height}")
    video_steps.append(
        f"crop={canvas_width}:{canvas_height}:"
        f"{(scaled_width - canvas_width) // 2}:"
        f"{(scaled_height - canvas_height) // 2}"
    )
    video_steps.append(f"setpts=PTS/{params.speed:.6f}")

    chains = [f"[0:v]{','.join(video_steps)}[base]"]

    # Camada de cor por cima, com alpha baixo. Antes o vídeo é que ficava
    # transparente sobre um fundo colorido, o que lavava a imagem inteira;
    # um véu sutil altera os pixels sem estragar o resultado.
    if params.tint_opacity > 0:
        chains.append(
            f"color=c=0x{params.background_color}:"
            f"s={canvas_width}x{canvas_height}[tint_src]"
        )
        chains.append(
            f"[tint_src]format=yuva420p,"
            f"colorchannelmixer=aa={params.tint_opacity:.4f}[tint]"
        )
        chains.append("[base][tint]overlay=0:0:shortest=1[composed]")
    else:
        chains.append("[base]null[composed]")

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
        # `normalize=0` é essencial: com a normalização padrão o amix divide
        # tudo pelo número de entradas e o áudio original perde 6 dB — metade
        # do volume — só por existir uma faixa de ruído junto.
        # O peso mantém o ruído dezenas de dB abaixo do som original, presente
        # no sinal mas fora do que se escuta.
        chains.append(
            f"[a_original][a_noise]amix=inputs=2:duration=first:"
            f"dropout_transition=0:weights=1 {NOISE_MIX_WEIGHT}:"
            f"normalize=0[aout]"
        )
        maps.append("[aout]")
    elif len(audio_sources) == 1:
        maps.append(f"[{audio_sources[0]}]")

    return ";".join(chains), maps


def _metadata_arguments(params: VariationParams) -> list[str]:
    """Monta os pares `-metadata chave=valor` da variação.

    Cada valor entra como um único argumento da lista; nada é interpolado
    numa string de comando, então um valor com `;` ou `$()` é apenas texto.
    """
    metadados: dict[str, str] = {}
    if params.metadata_title:
        metadados["title"] = params.metadata_title
    if params.metadata_author:
        metadados["artist"] = params.metadata_author
    metadados.update(params.metadata_extra)

    argumentos: list[str] = []
    for chave, valor in metadados.items():
        argumentos.extend(["-metadata", f"{chave}={valor}"])
    return argumentos


def build_metadata_only_command(
    *,
    ffmpeg_path: str,
    input_video: Path,
    output_path: Path,
    params: VariationParams,
) -> list[str]:
    """Comando que só reescreve os metadados, sem reencodar.

    `-c copy` copia os streams bit a bit: a imagem e o som saem idênticos ao
    original e o arquivo fica pronto em frações de segundo. O que muda é o
    contêiner e os metadados — o suficiente para o arquivo ter outro hash.
    """
    command = [
        ffmpeg_path,
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-i",
        str(input_video),
        "-map",
        "0",
        "-c",
        "copy",
        # Descarta os metadados do arquivo de origem antes de gravar os
        # novos; sem isto os campos antigos sobreviveriam ao lado.
        "-map_metadata",
        "-1",
        # Sem isto o muxer grava `encoder=LavfXX.YY`, uma assinatura idêntica
        # em todo arquivo gerado e que denuncia a ferramenta usada.
        "-fflags",
        "+bitexact",
    ]
    command.extend(_metadata_arguments(params))
    command.extend(["-movflags", "+faststart"])
    command.append(str(output_path))
    return command


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

    command.extend(_metadata_arguments(params))

    command.extend(["-fflags", "+bitexact"])
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
    mode: ProcessingMode = ProcessingMode.FULL,
) -> VariationResult:
    """Renderiza uma variação e devolve o resultado.

    Nunca levanta exceção por falha do FFmpeg: a falha vira um
    VariationResult com status FAILED, para que uma variação ruim não
    derrube o batch inteiro.
    """
    output_path = output_dir / f"{params.variation_id}.mp4"
    ffmpeg_path = find_binary("ffmpeg")

    if mode is ProcessingMode.METADATA_ONLY:
        command = build_metadata_only_command(
            ffmpeg_path=ffmpeg_path,
            input_video=input_video,
            output_path=output_path,
            params=params,
        )
    else:
        command = build_command(
            ffmpeg_path=ffmpeg_path,
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
        logger.warning(
            "ffmpeg excedeu o tempo limite",
            extra={
                "event": "ffmpeg.timeout",
                "variation_id": params.variation_id,
                "timeout_seconds": timeout_seconds,
                "input_resolution": f"{info.width}x{info.height}",
                "input_duration_seconds": round(info.duration_seconds, 1),
            },
        )
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
        # O stderr completo fica no log do servidor, e só ele: a resposta ao
        # cliente leva uma linha resumida. Sem isto, diagnosticar uma falha
        # que só acontece em produção vira adivinhação — o motivo real (falta
        # de memória, codec, processo morto pelo sistema) mora aqui.
        logger.error(
            "ffmpeg falhou",
            extra={
                "event": "ffmpeg.failed",
                "variation_id": params.variation_id,
                "returncode": process.returncode,
                "duration_seconds": round(elapsed, 2),
                "stderr": message[-2000:],
            },
        )
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
        md5=await asyncio.to_thread(compute_md5, output_path),
    )


def compute_md5(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Calcula o MD5 do arquivo lendo em blocos.

    Em blocos porque um vídeo pode ter centenas de MB e carregá-lo inteiro
    na memória só para somar o hash não se justifica.
    """
    digest = hashlib.md5()
    with path.open("rb") as arquivo:
        while bloco := arquivo.read(chunk_size):
            digest.update(bloco)
    return digest.hexdigest()
