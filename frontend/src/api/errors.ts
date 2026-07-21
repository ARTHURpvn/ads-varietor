import type { ProblemDetails } from './types.ts';

/**
 * Contexto da requisição que falhou. Serve só para escolher uma
 * mensagem mais precisa para o mesmo código de status.
 */
export type ErrorContext = 'upload' | 'status' | 'download' | 'cancel';

export interface ApiErrorOptions {
  /** null quando a requisição sequer chegou ao servidor. */
  status: number | null;
  context: ErrorContext;
  problem?: ProblemDetails | undefined;
  retryAfterSeconds?: number | undefined;
}

/**
 * Erro de API já traduzido para linguagem de usuário final.
 * A UI mostra apenas `userMessage` — nunca código HTTP, stack ou path.
 */
export class ApiError extends Error {
  readonly status: number | null;
  readonly context: ErrorContext;
  readonly problem: ProblemDetails | undefined;
  readonly retryAfterSeconds: number | undefined;
  readonly isOffline: boolean;

  constructor(options: ApiErrorOptions) {
    const userMessage = buildUserMessage(options);
    super(userMessage);
    this.name = 'ApiError';
    this.status = options.status;
    this.context = options.context;
    this.problem = options.problem;
    this.retryAfterSeconds = options.retryAfterSeconds;
    this.isOffline = options.status === null;
  }

  get userMessage(): string {
    return this.message;
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

/** Mensagem genérica usada quando nada mais se aplica. */
export const MENSAGEM_INDISPONIVEL =
  'O serviço não conseguiu responder ao seu pedido agora. ' +
  'Tente novamente em alguns instantes.';

/**
 * Falha de rede/conexão: a requisição nem chegou ao servidor.
 * Merece texto próprio — a ação do usuário aqui é checar a internet.
 */
export const MENSAGEM_SEM_CONEXAO =
  'Não conseguimos falar com o serviço. ' +
  'Verifique sua conexão e tente de novo.';

/**
 * Formatos de vídeo aceitos no upload. Fonte única: usada tanto na
 * validação local do arquivo quanto nas respostas 400/415 da API.
 */
export const MENSAGEM_ARQUIVO_INVALIDO =
  'Envie um arquivo de vídeo (MP4, MOV ou WebM).';

function buildUserMessage(options: ApiErrorOptions): string {
  const { status, context, problem, retryAfterSeconds } = options;

  if (status === null) {
    return MENSAGEM_SEM_CONEXAO;
  }

  switch (status) {
    case 400:
      return context === 'upload'
        ? MENSAGEM_ARQUIVO_INVALIDO
        : 'Não foi possível concluir a operação com esses dados.';

    case 401:
    case 403:
      return 'Seu acesso a este serviço não está liberado. ' +
        'Fale com quem administra o sistema.';

    case 404:
      return context === 'download'
        ? 'Este arquivo não está mais disponível para download.'
        : 'Não encontramos esse trabalho. Ele pode ter expirado.';

    case 409:
      return 'Este trabalho já foi finalizado e não pode mais ser alterado.';

    case 413:
      return 'O vídeo é grande demais. Envie um arquivo menor.';

    case 415:
      return MENSAGEM_ARQUIVO_INVALIDO;

    case 429:
      return retryAfterSeconds !== undefined
        ? `Muitos envios em pouco tempo. Tente de novo em ${formatSegundos(
            retryAfterSeconds,
          )}.`
        : 'Muitos envios em pouco tempo. Aguarde um instante e tente de novo.';

    case 507:
      return 'O servidor está sem espaço para novos vídeos. ' +
        'Tente novamente mais tarde.';

    default:
      break;
  }

  if (status >= 500) {
    return 'O serviço apresentou uma falha ao processar seu pedido. ' +
      'Tente novamente em alguns instantes.';
  }

  // Último recurso: usa o `detail` só se ele parecer texto de usuário.
  if (problem !== undefined && ehTextoSeguroParaUsuario(problem.detail)) {
    return problem.detail;
  }

  return MENSAGEM_INDISPONIVEL;
}

/**
 * Rejeita texto vindo da API que contenha path de sistema, stack
 * trace, nome de exceção ou código HTTP cru. Usado no `detail` do
 * problem+json e no `error` do job antes de mostrá-los na tela.
 */
export function ehTextoSeguroParaUsuario(valor: unknown): valor is string {
  if (typeof valor !== 'string') {
    return false;
  }

  const texto = valor.trim();
  if (texto.length === 0 || texto.length > 200) {
    return false;
  }

  const padroesProibidos = [
    /\//,
    /\\/,
    /Traceback/i,
    // Sem exigir os dois-pontos: nomes de exceção soltos no meio da frase
    // (KeyError, ValueError, OSError) passariam por um padrão /Error:/.
    /\w*Error\b/i,
    /\w*Exception\b/i,
    /Traceback/i,
    /\bat\s+\w+\.\w+/,
    /\b[45]\d{2}\b/,
  ];

  return !padroesProibidos.some((padrao) => padrao.test(texto));
}

function formatSegundos(segundos: number): string {
  if (segundos < 60) {
    return `${Math.max(1, Math.round(segundos))} segundos`;
  }

  const minutos = Math.ceil(segundos / 60);
  return minutos === 1 ? '1 minuto' : `${minutos} minutos`;
}
