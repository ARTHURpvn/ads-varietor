import type { JobStatus, Variation, VariationStatus } from '../api/types.ts';

/** Rótulo do status do trabalho em linguagem de usuário final. */
export function rotuloDoStatusDoJob(status: JobStatus): string {
  switch (status) {
    case 'pending':
      return 'Na fila';
    case 'running':
      return 'Gerando variações';
    case 'completed':
      return 'Concluído';
    case 'failed':
      return 'Não foi possível concluir';
    case 'cancelled':
      return 'Cancelado por você';
    case 'expired':
      return 'Expirado';
  }
}

export function rotuloDoStatusDaVariacao(status: VariationStatus): string {
  switch (status) {
    case 'pending':
      return 'Na fila';
    case 'running':
      return 'Gerando';
    case 'completed':
      return 'Pronta';
    case 'failed':
      return 'Falhou';
  }
}

const MOTIVO_FALHA_GENERICO =
  'Não foi possível gerar esta variação. Tente gerar novamente.';

/**
 * Traduz o motivo técnico da falha de uma variação para algo que o
 * usuário entenda. Nunca expõe path, stack ou código de erro.
 */
export function motivoDaFalha(variacao: Variation): string {
  const erro = variacao.error?.toLowerCase() ?? '';

  if (erro.length === 0) {
    return MOTIVO_FALHA_GENERICO;
  }

  if (erro.includes('timeout') || erro.includes('timed out')) {
    return 'A geração demorou mais do que o permitido e foi interrompida.';
  }

  if (erro.includes('space') || erro.includes('disk') || erro.includes('enospc')) {
    return 'O servidor ficou sem espaço enquanto gerava esta variação.';
  }

  if (erro.includes('audio')) {
    return 'O áudio do vídeo não pôde ser processado nesta variação.';
  }

  if (
    erro.includes('codec') ||
    erro.includes('decode') ||
    erro.includes('invalid data') ||
    erro.includes('corrupt')
  ) {
    return 'O formato deste vídeo não pôde ser lido nesta variação.';
  }

  if (erro.includes('cancel')) {
    return 'Esta variação foi interrompida quando o trabalho foi cancelado.';
  }

  if (erro.includes('memory')) {
    return 'O vídeo é pesado demais para ser processado com estes ajustes.';
  }

  return MOTIVO_FALHA_GENERICO;
}

/** Descrição curta dos parâmetros aplicados na variação. */
export function resumoDosParametros(variacao: Variation): string {
  const { params } = variacao;
  const partes = [
    `velocidade ${params.speed.toFixed(2)}x`,
    `${params.filter_type} ${params.filter_value.toFixed(2)}`,
    `escala ${params.video_scale.toFixed(2)}x`,
    `fundo ${params.background_color}`,
  ];

  if (params.noise_audio) {
    partes.push('ruído no áudio');
  }

  return partes.join(' · ');
}
