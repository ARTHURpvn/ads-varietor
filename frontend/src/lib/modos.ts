/**
 * Textos e metadados dos modos de processamento, em linguagem de usuário
 * final. Fonte única: tela de envio, progresso, resultados e cartões leem
 * daqui em vez de repetir a explicação de cada modo.
 */

import type { ProcessingMode } from '../api/types.ts';

export interface DescricaoDeModo {
  modo: ProcessingMode;
  /** Rótulo da opção no seletor. */
  titulo: string;
  /** Explicação do que acontece com o arquivo. */
  descricao: string;
  /** Destaque de tempo — é a diferença que decide a escolha. */
  etiquetaDeTempo: string;
  /** true quando o modo termina em menos de um segundo. */
  rapido: boolean;
}

/** Modo pré-selecionado no envio. Também é o padrão do backend. */
export const MODO_PADRAO: ProcessingMode = 'full';

const POR_MODO: Record<ProcessingMode, DescricaoDeModo> = {
  full: {
    modo: 'full',
    titulo: 'Gerar variações do vídeo',
    descricao:
      'Cada cópia sai com a imagem levemente diferente da original: ' +
      'velocidade, cor e enquadramento mudam um pouco.',
    etiquetaDeTempo: 'Mais lento · alguns minutos',
    rapido: false,
  },
  metadata_only: {
    modo: 'metadata_only',
    titulo: 'Só trocar a identidade do arquivo',
    descricao:
      'A imagem e o som ficam idênticos ao original. Muda só a ' +
      'identificação interna de cada arquivo, que é o que evita ele ser ' +
      'tratado como repetido.',
    etiquetaDeTempo: 'Quase instantâneo · menos de 1s',
    rapido: true,
  },
};

/** Opções na ordem em que aparecem no seletor. */
export const MODOS: readonly DescricaoDeModo[] = [
  POR_MODO.full,
  POR_MODO.metadata_only,
];

export function descricaoDoModo(modo: ProcessingMode): DescricaoDeModo {
  return POR_MODO[modo];
}

/**
 * Como chamar os arquivos gerados. Em `metadata_only` nada varia de fato
 * na imagem, então "variações" seria enganoso.
 */
export function rotuloDasSaidas(modo: ProcessingMode): string {
  return modo === 'metadata_only' ? 'cópias' : 'variações';
}

/** Versão no singular de {@link rotuloDasSaidas}. */
export function rotuloDaSaida(modo: ProcessingMode): string {
  return modo === 'metadata_only' ? 'cópia' : 'variação';
}

/** Versão no singular com inicial maiúscula, para título de cartão. */
export function tituloDaSaida(modo: ProcessingMode): string {
  return modo === 'metadata_only' ? 'Cópia' : 'Variação';
}
