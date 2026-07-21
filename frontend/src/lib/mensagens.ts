import { ehTextoSeguroParaUsuario } from '../api/errors.ts';
import {
  isTerminalStatus,
  type Job,
  type JobStatus,
  type ProcessingMode,
  type Variation,
  type VariationParams,
  type VariationStatus,
} from '../api/types.ts';
import type { AnaliseDeHashes } from './hash.ts';
import { MODO_PADRAO, rotuloDasSaidas } from './modos.ts';

/**
 * Rótulo do status do trabalho em linguagem de usuário final. O modo muda
 * só o texto de "em andamento": em `metadata_only` nada é "gerado", os
 * arquivos são apenas preparados.
 */
export function rotuloDoStatusDoJob(
  status: JobStatus,
  modo: ProcessingMode = MODO_PADRAO,
): string {
  switch (status) {
    case 'pending':
      return 'Na fila';
    case 'running':
      return modo === 'metadata_only'
        ? 'Preparando as cópias'
        : 'Gerando variações';
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
 * O backend marca como `failed` a variação que o cancelamento pegou no
 * meio da renderização. Chamar isso de falha é errado: nada quebrou, o
 * usuário mandou parar. Só vale para o job cancelado e quando o erro não
 * descreve um problema real (vazio ou falando do próprio cancelamento).
 */
export function ehInterrupcaoPorCancelamento(
  variacao: Variation,
  statusDoJob: JobStatus,
): boolean {
  if (statusDoJob !== 'cancelled' || variacao.status !== 'failed') {
    return false;
  }

  const erro = (variacao.error ?? '').trim().toLowerCase();

  return erro.length === 0 || erro.includes('cancel');
}

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

  if (ehInterrupcaoPorCancelamento(variacao, statusDoJob)) {
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

/**
 * Nome do efeito de cor em português, na palavra que um editor de vídeo
 * usa. As chaves são os valores do enum `FilterType` da API.
 *
 * `none` não entra: é a ausência de efeito e não tem o que descrever.
 * Qualquer valor fora desta tabela também é omitido — melhor mostrar um
 * parâmetro a menos do que despejar o enum em inglês na tela.
 */
const ROTULO_DO_FILTRO: Readonly<Record<string, string>> = {
  brightness: 'brilho',
  contrast: 'contraste',
  saturate: 'saturação',
  hue: 'matiz',
};

/**
 * Trecho que descreve o efeito de cor. `null` quando não há efeito algum
 * — o `none` da API — ou quando o tipo é desconhecido.
 */
export function descricaoDoFiltro(params: VariationParams): string | null {
  const rotulo = ROTULO_DO_FILTRO[params.filter_type];

  if (rotulo === undefined) {
    return null;
  }

  return `${rotulo} ${params.filter_value.toFixed(2)}`;
}

/** Descrição curta dos parâmetros aplicados na variação. */
export function resumoDosParametros(variacao: Variation): string {
  const { params } = variacao;
  const filtro = descricaoDoFiltro(params);
  const partes = [
    `velocidade ${params.speed.toFixed(2)}x`,
    ...(filtro !== null ? [filtro] : []),
    `escala ${params.video_scale.toFixed(2)}x`,
    `fundo ${params.background_color}`,
  ];

  if (params.noise_audio) {
    partes.push('ruído no áudio');
  }

  return partes.join(' · ');
}

const RESUMO_SEM_REPROCESSAMENTO =
  'Imagem e som idênticos ao original — só a identificação interna mudou.';

/**
 * Descrição do que mudou naquele arquivo. Em `metadata_only` os parâmetros
 * de vídeo não são aplicados: mostrá-los faria o usuário procurar por uma
 * diferença de imagem que não existe.
 */
export function resumoDaVariacao(
  variacao: Variation,
  modo: ProcessingMode,
): string {
  if (modo === 'metadata_only') {
    return RESUMO_SEM_REPROCESSAMENTO;
  }

  return resumoDosParametros(variacao);
}

function pluralizar(
  quantidade: number,
  singular: string,
  plural: string,
): string {
  return quantidade === 1 ? singular : plural;
}

/**
 * Texto da conferência de unicidade dos hashes. Só é chamado quando há
 * pelo menos um hash conhecido — sem isso não há o que afirmar.
 */
export function mensagemDaVerificacaoDeHashes(
  analise: AnaliseDeHashes,
  modo: ProcessingMode,
): string {
  const pendentes =
    analise.semHash > 0
      ? ` ${analise.semHash} ${pluralizar(
          analise.semHash,
          'arquivo ainda não tem',
          'arquivos ainda não têm',
        )} identificação registrada.`
      : '';

  if (analise.tudoDistinto) {
    return (
      `Conferimos ${analise.comHash} ` +
      `${pluralizar(analise.comHash, 'identificação', 'identificações')}: ` +
      'nenhuma se repete e nenhuma é igual à do arquivo original.' +
      pendentes
    );
  }

  const problemas: string[] = [];

  if (analise.duplicados.length > 0) {
    problemas.push(
      `${analise.duplicados.length} ` +
        `${pluralizar(
          analise.duplicados.length,
          'identificação aparece',
          'identificações aparecem',
        )} em mais de um arquivo.`,
    );
  }

  if (analise.repetemOOriginal > 0) {
    problemas.push(
      `${analise.repetemOOriginal} ` +
        `${pluralizar(
          analise.repetemOOriginal,
          'arquivo ficou idêntico',
          'arquivos ficaram idênticos',
        )} ao original.`,
    );
  }

  return (
    `${problemas.join(' ')} Esses arquivos podem ser tratados como ` +
    `repetidos. Gere as ${rotuloDasSaidas(modo)} de novo.${pendentes}`
  );
}
