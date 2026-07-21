import { describe, expect, it } from 'vitest';

import {
  ApiError,
  MENSAGEM_INDISPONIVEL,
  MENSAGEM_SEM_CONEXAO,
} from '../api/errors.ts';
import { ehFalhaDeConexao, mensagemDeErro, tituloDeErro } from './erro.ts';

const semConexao = new ApiError({ status: null, context: 'status' });
const erroDoServidor = new ApiError({ status: 500, context: 'status' });

describe('mensagemDeErro', () => {
  it('test_pede_para_checar_a_internet_quando_a_requisicao_nao_chegou_ao_servidor', () => {
    expect(mensagemDeErro(semConexao)).toBe(MENSAGEM_SEM_CONEXAO);
  });

  it('test_usa_mensagem_distinta_da_de_conexao_quando_o_servidor_falhou', () => {
    const mensagem = mensagemDeErro(erroDoServidor);

    expect(mensagem).not.toBe(MENSAGEM_SEM_CONEXAO);
    expect(mensagem).toBe(
      'O serviço apresentou uma falha ao processar seu pedido. ' +
        'Tente novamente em alguns instantes.',
    );
  });

  it('test_cai_na_mensagem_generica_quando_o_erro_nao_e_da_api', () => {
    expect(mensagemDeErro(new TypeError('fetch failed'))).toBe(
      MENSAGEM_INDISPONIVEL,
    );
  });

  it.each([[undefined], [null], ['algo deu errado'], [42]])(
    'test_cai_na_mensagem_generica_quando_o_valor_lancado_nao_e_erro (%s)',
    (valor) => {
      expect(mensagemDeErro(valor)).toBe(MENSAGEM_INDISPONIVEL);
    },
  );

  it('test_nunca_expoe_stack_nem_codigo_http_quando_o_erro_e_tecnico', () => {
    const tecnico = new Error(
      'Request failed with status code 500 at /srv/app/main.py',
    );

    const mensagem = mensagemDeErro(tecnico);

    expect(mensagem).not.toContain('500');
    expect(mensagem).not.toContain('/srv');
  });
});

describe('ehFalhaDeConexao', () => {
  it('test_reconhece_falha_de_conexao_quando_o_status_e_nulo', () => {
    expect(ehFalhaDeConexao(semConexao)).toBe(true);
  });

  it('test_nao_reconhece_falha_de_conexao_quando_ha_status_http', () => {
    expect(ehFalhaDeConexao(erroDoServidor)).toBe(false);
  });

  it('test_nao_reconhece_falha_de_conexao_quando_o_erro_e_desconhecido', () => {
    expect(ehFalhaDeConexao(new Error('boom'))).toBe(false);
  });
});

describe('tituloDeErro', () => {
  it('test_titula_como_sem_conexao_quando_a_api_esta_inalcancavel', () => {
    expect(tituloDeErro(semConexao)).toBe('Sem conexão com o serviço');
  });

  it('test_titula_como_indisponivel_quando_o_servidor_respondeu_com_erro', () => {
    expect(tituloDeErro(erroDoServidor)).toBe(
      'Serviço indisponível no momento',
    );
  });
});
