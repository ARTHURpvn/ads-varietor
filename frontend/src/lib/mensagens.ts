import { ehTextoSeguroParaUsuario } from '../api/errors.ts';
import {
  isTerminalStatus,
  type Job,
  type JobStatus,
  type Variation,
  type VariationStatus,
} from '../api/types.ts';

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

/**
 * Status mostrado no cartão da variação. `interrompida` não existe na
 * API: é o que a UI mostra quando o trabalho terminou (cancelado,
 * expirado ou com falha) e a variação nunca saiu da fila.
 */
export type StatusExibidoDaVariacao = VariationStatus | 'interrompida';

/**
 * Uma variação ainda 'pending'/'running' num trabalho já encerrado não
 * vai mais avançar — mostrá-la como "Na fila" para sempre seria mentira.
 */
export function statusExibidoDaVariacao(
  variacao: Variation,
  statusDoJob: JobStatus,
): StatusExibidoDaVariacao {
  const aindaNaFila =
    variacao.status === 'pending' || variacao.status === 'running';

  if (aindaNaFila && isTerminalStatus(statusDoJob)) {
    return 'interrompida';
  }

  return variacao.status;
}

export function rotuloDoStatusDaVariacao(
  status: StatusExibidoDaVariacao,
): string {
  switch (status) {
    case 'pending':
      return 'Na fila';
    case 'running':
      return 'Gerando';
    case 'completed':
      return 'Pronta';
    case 'failed':
      return 'Falhou';
    case 'interrompida':
      return 'Interrompida';
  }
}

const MOTIVO_FALHA_GENERICO =
  'Não foi possível gerar esta variação. Tente gerar novamente.';

/**
 * Traduz o motivo técnico da falha de uma variação para algo que o
 * usuário entenda. Nunca expõe path, stack ou código de erro.
 *
 * A API grava dois formatos em `variation.error`:
 * - "Tempo de processamento excedido (300s)." — texto nosso, em PT-BR;
 * - "Falha ao renderizar: <última linha do FFmpeg>" — prefixo em PT-BR
 *   com a cauda vinda do FFmpeg, que fala inglês. Por isso o casamento
 *   cobre as duas línguas.
 */
export function motivoDaFalha(variacao: Variation): string {
  const erro = variacao.error?.toLowerCase() ?? '';

  if (erro.length === 0) {
    return MOTIVO_FALHA_GENERICO;
  }

  if (
    erro.includes('tempo de processamento excedido') ||
    erro.includes('timeout') ||
    erro.includes('timed out')
  ) {
    return 'A geração demorou mais do que o permitido e foi interrompida.';
  }

  if (
    erro.includes('sem espaço') ||
    erro.includes('no space') ||
    erro.includes('enospc') ||
    erro.includes('disk')
  ) {
    return 'O servidor ficou sem espaço enquanto gerava esta variação.';
  }

  if (erro.includes('áudio') || erro.includes('audio')) {
    return 'O áudio do vídeo não pôde ser processado nesta variação.';
  }

  if (
    erro.includes('codec') ||
    erro.includes('decode') ||
    erro.includes('decoder') ||
    erro.includes('invalid data') ||
    erro.includes('corrupt') ||
    erro.includes('formato')
  ) {
    return 'O formato deste vídeo não pôde ser lido nesta variação.';
  }

  if (erro.includes('cancel')) {
    return 'Esta variação foi interrompida quando o trabalho foi cancelado.';
  }

  if (erro.includes('memory') || erro.includes('memória')) {
    return 'O vídeo é pesado demais para ser processado com estes ajustes.';
  }

  if (erro.includes('falha ao renderizar')) {
    return 'O servidor não conseguiu renderizar esta variação.';
  }

  return MOTIVO_FALHA_GENERICO;
}

/** Explica por que uma variação ficou pelo caminho. */
export function motivoDaInterrupcao(statusDoJob: JobStatus): string {
  if (statusDoJob === 'cancelled') {
    return 'Esta variação não ficou pronta porque você cancelou a geração.';
  }

  if (statusDoJob === 'expired') {
    return 'Esta variação não ficou pronta antes de o trabalho expirar.';
  }

  return 'Esta variação não chegou a ser gerada.';
}

/**
 * Motivo da falha do trabalho inteiro, vindo da API. Só é mostrado se
 * o texto passar no filtro de segurança — nada de stack ou path.
 */
export function motivoDaFalhaDoJob(job: Job): string {
  if (ehTextoSeguroParaUsuario(job.error)) {
    return job.error;
  }

  return 'Não conseguimos processar este vídeo.';
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
