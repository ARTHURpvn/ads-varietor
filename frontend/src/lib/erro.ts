import {
  isApiError,
  MENSAGEM_INDISPONIVEL,
  MENSAGEM_SEM_CONEXAO,
} from '../api/errors.ts';

/**
 * Converte qualquer erro em texto para o usuário final.
 * Nunca vaza código HTTP, stack trace ou path de sistema.
 */
export function mensagemDeErro(erro: unknown): string {
  if (ehFalhaDeConexao(erro)) {
    return MENSAGEM_SEM_CONEXAO;
  }

  if (isApiError(erro)) {
    return erro.userMessage;
  }

  return MENSAGEM_INDISPONIVEL;
}

/** Indica falha de conexão com o serviço (API fora do ar). */
export function ehFalhaDeConexao(erro: unknown): boolean {
  return isApiError(erro) && erro.isOffline;
}

/** Título do alerta de erro, ajustado ao tipo de falha. */
export function tituloDeErro(erro: unknown): string {
  return ehFalhaDeConexao(erro)
    ? 'Sem conexão com o serviço'
    : 'Serviço indisponível no momento';
}
