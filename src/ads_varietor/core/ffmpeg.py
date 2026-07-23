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
from collections.abc import Awaitable, Callable
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
# por volta de -50 a -42 dB, contra -21 dB de um áudio comum: um chiado de
# fundo audível, com o som original bem acima dele.
NOISE_MIX_WEIGHT = 0.5
# `ultrafast` encoda pouco mais rápido e gera arquivo 2 a 3 vezes maior — o
# que se paga de volta em escrita de disco, montagem do ZIP e download.
DEFAULT_PRESET = "veryfast"

logger = logging.getLogger(__name__)

# Recebe a fração concluída de uma variação, de 0 a 1.
ProgressoCallback = Callable[[float], Awaitable[None]]


class FilterGraphError(ValueError):
    """Os parâmetros recebidos não produzem um filtergraph válido."""


async def _vazio() -> bytes:
    """Stand-in para quando não há stream de erro a ler."""
    return b""


async def _acompanhar_progresso(
    stdout: asyncio.StreamReader,
    *,
    duracao_total: float,
    on_progress: ProgressoCallback,
) -> None:
    """Lê o fluxo de `-progress` do FFmpeg e reporta a fração concluída.

    O FFmpeg escreve blocos de `chave=valor`, um por linha, terminados por
    `progress=continue` ou `progress=end`. O que interessa é `out_time_us`:
    quanto do vídeo de saída já foi escrito.
    """
    if duracao_total <= 0:
        return

    while True:
        linha = await stdout.readline()
        if not linha:
            return

        chave, _, valor = linha.decode("utf-8", errors="replace").strip().partition("=")
        if chave == "out_time_us":
            try:
                segundos = int(valor) / 1_000_000
            except ValueError:
                # `out_time_us=N/A` aparece nos primeiros blocos, antes de o
                # encode produzir qualquer frame.
                continue
            await on_progress(min(1.0, max(0.0, segundos / duracao_total)))
        elif chave == "progress" and valor == "end":
            await on_progress(1.0)
            return


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

    # Zoom feito como CROP e depois SCALE, e não o contrário.
    #
    # Ampliar para 105% e cortar de volta dá a mesma imagem que recortar a
    # região central e ampliar até o tamanho original — mas na primeira
    # ordem o scaler processa MAIS pixels que o vídeo tem, e na segunda
    # processa menos. Para zoom de 1,05 em 1080p a diferença é de 2,28
    # milhões de pixels por frame contra 1,87 milhão.
    cropped_width = _to_even(int(canvas_width / params.video_scale))
    cropped_height = _to_even(int(canvas_height / params.video_scale))

    # --- Cadeia de vídeo -------------------------------------------------
    video_steps: list[str] = []
    color_filter = _build_color_filter(params)
    if color_filter:
        video_steps.append(color_filter)

    if (cropped_width, cropped_height) != (canvas_width, canvas_height):
        video_steps.append(
            f"crop={cropped_width}:{cropped_height}:"
            f"{(canvas_width - cropped_width) // 2}:"
            f"{(canvas_height - cropped_height) // 2}"
        )
        video_steps.append(f"scale={canvas_width}:{canvas_height}")
    elif (info.width, info.height) != (canvas_width, canvas_height):
        # Sem zoom, mas a entrada tem lado ímpar. libx264 com yuv420p exige
        # dimensão par, então o quadro é aparado no mínimo necessário.
        video_steps.append(f"crop={canvas_width}:{canvas_height}:0:0")

    # Véu de cor: um `drawbox` preenchendo o quadro com a cor num alpha
    # baixo. É um filtro só, e desta vez de verdade sutil.
    #
    # O `colorize` que estava aqui NÃO servia: o parâmetro `mix` dele
    # controla o quanto do brilho original é preservado, não a intensidade
    # da cor — ele sempre aplicava a cor cheia, então `mix=0.06` tingia o
    # vídeo inteiro de laranja em vez de dar um tom leve. O `drawbox` com
    # `color@alpha` mistura de verdade só o alpha pedido.
    if params.tint_opacity > 0:
        video_steps.append(
            f"drawbox=w=iw:h=ih:t=fill"
            f":color=0x{params.background_color}@{params.tint_opacity:.4f}"
        )

    video_steps.append(f"setpts=PTS/{params.speed:.6f}")

    chains = [f"[0:v]{','.join(video_steps)}[composed]"]

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
        # A atenuação vai num filtro `volume` próprio, e não no `weights` do
        # amix: `weights=1 0.15` carrega um espaço, e espaço não escapado no
        # meio do valor de uma opção de filtergraph é ambíguo para o parser.
        chains.append(
            f"anoisesrc=a={params.noise_level:.4f}:d={noise_duration:.3f}"
            f":c=pink[a_noise_bruto]"
        )
        chains.append(
            f"[a_noise_bruto]volume={NOISE_MIX_WEIGHT}[a_noise]"
        )
        audio_sources.append("a_noise")

    if len(audio_sources) == 2:
        # `normalize=0` é essencial: com a normalização padrão o amix divide
        # tudo pelo número de entradas e o áudio original perderia 6 dB —
        # metade do volume — só por existir uma faixa de ruído junto.
        # O ruído já vem atenuado pelo `volume` acima, então aqui é só somar.
        chains.append(
            "[a_original][a_noise]amix=inputs=2:duration=first:"
            "dropout_transition=0:normalize=0[aout]"
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
    preset: str = DEFAULT_PRESET,
    threads: int = 0,
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
    # Threads por processo. Com vários FFmpeg simultâneos, deixar cada um
    # abrir quantas quiser gera mais threads que núcleos e o tempo vai para
    # troca de contexto em vez de encode.
    if threads > 0:
        command.extend(["-threads", str(threads)])

    command.extend(["-c:v", "libx264", "-preset", preset, "-crf", "23"])
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
    preset: str = DEFAULT_PRESET,
    threads: int = 0,
    on_progress: ProgressoCallback | None = None,
) -> VariationResult:
    """Renderiza uma variação e devolve o resultado.

    Nunca levanta exceção por falha do FFmpeg: a falha vira um
    VariationResult com status FAILED, para que uma variação ruim não
    derrube o batch inteiro.

    `on_progress` recebe a fração já concluída desta variação, de 0 a 1,
    conforme o FFmpeg avança.
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
            preset=preset,
            threads=threads,
        )

    # `-progress pipe:1` faz o FFmpeg publicar o andamento em stdout, em
    # blocos de chave=valor. Sem isso só dá para saber que uma variação
    # começou e terminou, e a barra anda aos saltos.
    acompanhar = on_progress is not None and mode is not ProcessingMode.METADATA_ONLY
    if acompanhar:
        command = [command[0], "-progress", "pipe:1", "-nostats", *command[1:]]

    loop = asyncio.get_running_loop()
    started_at = loop.time()
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE if acompanhar else asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )

    # `communicate()` só retorna quando o processo termina, e aqui é preciso
    # ler stdout enquanto ele roda. Os dois fluxos viram tasks próprias; sem
    # isso, um stderr grande poderia encher o buffer e travar o FFmpeg.
    tarefa_stderr = asyncio.create_task(
        process.stderr.read() if process.stderr else _vazio()
    )
    tarefa_progresso: asyncio.Task[None] | None = None
    if acompanhar and process.stdout is not None and on_progress is not None:
        tarefa_progresso = asyncio.create_task(
            _acompanhar_progresso(
                process.stdout,
                duracao_total=info.duration_seconds / params.speed,
                on_progress=on_progress,
            )
        )

    def _encerrar_leitores() -> None:
        if tarefa_progresso is not None:
            tarefa_progresso.cancel()

    try:
        await asyncio.wait_for(process.wait(), timeout=timeout_seconds)
        stderr = await tarefa_stderr
        _encerrar_leitores()
    except asyncio.TimeoutError:
        _encerrar_leitores()
        tarefa_stderr.cancel()
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
        _encerrar_leitores()
        tarefa_stderr.cancel()
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
