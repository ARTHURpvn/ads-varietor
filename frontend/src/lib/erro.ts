import { isApiError, MENSAGEM_INDISPONIVEL } from '../api/errors.ts';

/**
 * Converte qualquer erro em texto para o usuário final.
 * Nunca vaza código HTTP, stack trace ou path de sistema.
 */
export function mensagemDeErro(erro: unknown): string {
  if (isApiError(erro)) {
    return erro.userMessage;
  }

  return MENSAGEM_INDISPONIVEL;
}

/** Indica falha de conexão com o serviço (API fora do ar). */
export function ehFalhaDeConexao(erro: unknown): boolean {
  return isApiError(erro) && erro.isOffline;
}
