/** Validação de arquivo de vídeo no cliente (antes de subir). */

export const MENSAGEM_ARQUIVO_INVALIDO =
  'Envie um arquivo de vídeo (MP4, MOV ou WebM).';

const TIPOS_ACEITOS: readonly string[] = [
  'video/mp4',
  'video/quicktime',
  'video/webm',
  'video/x-m4v',
];

const EXTENSOES_ACEITAS: readonly string[] = ['.mp4', '.mov', '.webm', '.m4v'];

/** Valor do atributo `accept` do input file. */
export const ACCEPT_ATTRIBUTE = [...TIPOS_ACEITOS, ...EXTENSOES_ACEITAS].join(
  ',',
);

export type ValidacaoArquivo =
  | { valido: true; arquivo: File }
  | { valido: false; mensagem: string };

export function validarArquivoDeVideo(arquivo: File): ValidacaoArquivo {
  if (arquivo.size === 0) {
    return {
      valido: false,
      mensagem: 'Este arquivo está vazio. Escolha outro vídeo.',
    };
  }

  const tipoAceito = TIPOS_ACEITOS.includes(arquivo.type.toLowerCase());
  const nome = arquivo.name.toLowerCase();
  const extensaoAceita = EXTENSOES_ACEITAS.some((extensao) =>
    nome.endsWith(extensao),
  );

  if (!tipoAceito && !extensaoAceita) {
    return { valido: false, mensagem: MENSAGEM_ARQUIVO_INVALIDO };
  }

  return { valido: true, arquivo };
}

export function formatarTamanho(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }

  const unidades = ['KB', 'MB', 'GB'] as const;
  let valor = bytes / 1024;
  let indice = 0;

  while (valor >= 1024 && indice < unidades.length - 1) {
    valor /= 1024;
    indice += 1;
  }

  const unidade = unidades[indice] ?? 'GB';
  return `${valor.toFixed(valor >= 10 ? 0 : 1)} ${unidade}`;
}
