import { describe, expect, it } from 'vitest';

import {
  ApiError,
  ehTextoSeguroParaUsuario,
  isApiError,
  MENSAGEM_ARQUIVO_INVALIDO,
  MENSAGEM_INDISPONIVEL,
  MENSAGEM_SEM_CONEXAO,
  type ErrorContext,
} from './errors.ts';
import type { ProblemDetails } from './types.ts';

function mensagemDe(
  status: number | null,
  context: ErrorContext = 'status',
  extras: { problem?: ProblemDetails; retryAfterSeconds?: number } = {},
): string {
  return new ApiError({ status, context, ...extras }).userMessage;
}

function problema(detail: string, status = 422): ProblemDetails {
  return {
    type: 'about:blank',
    title: 'Erro',
    status,
    detail,
  };
}

describe('ApiError — mapeamento de status para mensagem', () => {
  it('test_avisa_sobre_conexao_quando_a_requisicao_nao_chegou_ao_servidor', () => {
    expect(mensagemDe(null)).toBe(MENSAGEM_SEM_CONEXAO);
    expect(new ApiError({ status: null, context: 'upload' }).isOffline).toBe(
      true,
    );
  });

  it('test_lista_os_formatos_aceitos_quando_o_upload_recebe_400', () => {
    expect(mensagemDe(400, 'upload')).toBe(MENSAGEM_ARQUIVO_INVALIDO);
  });

  it('test_usa_texto_neutro_quando_o_400_nao_e_de_upload', () => {
    expect(mensagemDe(400, 'cancel')).toBe(
      'Não foi possível concluir a operação com esses dados.',
    );
  });

  it.each([401, 403])(
    'test_manda_falar_com_o_administrador_quando_o_status_e_%i',
    (status) => {
      expect(mensagemDe(status)).toBe(
        'Seu acesso a este serviço não está liberado. ' +
          'Fale com quem administra o sistema.',
      );
    },
  );

  it('test_diz_que_o_arquivo_sumiu_quando_o_download_recebe_404', () => {
    expect(mensagemDe(404, 'download')).toBe(
      'Este arquivo não está mais disponível para download.',
    );
  });

  it('test_diz_que_o_trabalho_pode_ter_expirado_quando_o_status_recebe_404', () => {
    expect(mensagemDe(404, 'status')).toBe(
      'Não encontramos esse trabalho. Ele pode ter expirado.',
    );
  });

  it('test_diz_que_o_trabalho_ja_terminou_quando_o_status_e_409', () => {
    expect(mensagemDe(409, 'cancel')).toBe(
      'Este trabalho já foi finalizado e não pode mais ser alterado.',
    );
  });

  it('test_pede_arquivo_menor_quando_o_status_e_413', () => {
    expect(mensagemDe(413, 'upload')).toBe(
      'O vídeo é grande demais. Envie um arquivo menor.',
    );
  });

  it('test_lista_os_formatos_aceitos_quando_o_status_e_415', () => {
    expect(mensagemDe(415, 'upload')).toBe(MENSAGEM_ARQUIVO_INVALIDO);
  });

  it('test_avisa_sobre_espaco_no_servidor_quando_o_status_e_507', () => {
    expect(mensagemDe(507, 'upload')).toBe(
      'O servidor está sem espaço para novos vídeos. ' +
        'Tente novamente mais tarde.',
    );
  });

  it.each([500, 502, 503, 504])(
    'test_avisa_de_falha_do_servico_quando_o_status_e_%i',
    (status) => {
      expect(mensagemDe(status)).toBe(
        'O serviço apresentou uma falha ao processar seu pedido. ' +
          'Tente novamente em alguns instantes.',
      );
    },
  );

  it('test_cai_na_mensagem_generica_quando_o_status_e_desconhecido_e_nao_ha_problema', () => {
    expect(mensagemDe(418)).toBe(MENSAGEM_INDISPONIVEL);
  });

  it('test_nenhuma_mensagem_expoe_o_codigo_http_cru', () => {
    const statuses = [null, 400, 401, 403, 404, 409, 413, 415, 429, 500, 507];

    for (const status of statuses) {
      const mensagem = mensagemDe(status);
      if (status !== null) {
        expect(mensagem).not.toContain(String(status));
      }
      expect(mensagem).not.toMatch(/HTTP|status code/i);
    }
  });
});

describe('ApiError — 429 e Retry-After', () => {
  it('test_pede_apenas_para_aguardar_quando_nao_ha_retry_after', () => {
    expect(mensagemDe(429, 'upload')).toBe(
      'Muitos envios em pouco tempo. Aguarde um instante e tente de novo.',
    );
  });

  it('test_informa_os_segundos_quando_o_retry_after_e_menor_que_um_minuto', () => {
    expect(
      mensagemDe(429, 'upload', { retryAfterSeconds: 30 }),
    ).toBe('Muitos envios em pouco tempo. Tente de novo em 30 segundos.');
  });

  it('test_nunca_pede_para_esperar_zero_segundos_quando_o_retry_after_e_minusculo', () => {
    expect(mensagemDe(429, 'upload', { retryAfterSeconds: 0 })).toContain(
      '1 segundos',
    );
  });

  it('test_usa_minuto_no_singular_quando_o_retry_after_e_de_60s', () => {
    expect(mensagemDe(429, 'upload', { retryAfterSeconds: 60 })).toBe(
      'Muitos envios em pouco tempo. Tente de novo em 1 minuto.',
    );
  });

  it('test_arredonda_para_cima_em_minutos_quando_o_retry_after_passa_de_um_minuto', () => {
    expect(mensagemDe(429, 'upload', { retryAfterSeconds: 90 })).toBe(
      'Muitos envios em pouco tempo. Tente de novo em 2 minutos.',
    );
  });

  it('test_preserva_o_retry_after_no_erro_quando_informado', () => {
    const erro = new ApiError({
      status: 429,
      context: 'upload',
      retryAfterSeconds: 45,
    });

    expect(erro.retryAfterSeconds).toBe(45);
    expect(erro.status).toBe(429);
    expect(erro.isOffline).toBe(false);
  });
});

describe('ApiError — detalhe do problem+json', () => {
  it('test_mostra_o_detalhe_quando_o_texto_e_seguro_e_o_status_nao_tem_regra_propria', () => {
    const mensagem = mensagemDe(422, 'upload', {
      problem: problema('O número de variações precisa estar entre 1 e 50.'),
    });

    expect(mensagem).toBe('O número de variações precisa estar entre 1 e 50.');
  });

  it.each([
    ['path de sistema', '/srv/app/storage/jobs/abc.mp4'],
    ['path do windows', 'C:\\videos\\entrada.mp4'],
    ['traceback', 'Traceback (most recent call last)'],
    ['nome de excecao', 'ValidationException no campo speed'],
    ['prefixo de erro', 'Error: algo inesperado'],
    ['codigo http cru', 'Falhou com 503 do upstream'],
    ['quadro de stack', 'falhou at modulo.funcao'],
  ])(
    'test_esconde_o_detalhe_quando_ele_contem_%s',
    (_rotulo, detail) => {
      expect(mensagemDe(422, 'upload', { problem: problema(detail) })).toBe(
        MENSAGEM_INDISPONIVEL,
      );
    },
  );

  it('test_ignora_o_detalhe_quando_o_status_500_ja_tem_mensagem_propria', () => {
    const mensagem = mensagemDe(500, 'status', {
      problem: problema('detalhe interno legivel', 500),
    });

    expect(mensagem).not.toContain('detalhe interno legivel');
  });

  it('test_preserva_o_problema_no_erro_quando_informado', () => {
    const problem = problema('Mensagem segura.');
    const erro = new ApiError({ status: 422, context: 'upload', problem });

    expect(erro.problem).toEqual(problem);
    expect(erro.context).toBe('upload');
    expect(erro.name).toBe('ApiError');
  });
});

describe('ehTextoSeguroParaUsuario', () => {
  it('test_aceita_o_texto_quando_e_uma_frase_curta_em_portugues', () => {
    expect(ehTextoSeguroParaUsuario('O vídeo enviado não pôde ser lido.')).toBe(
      true,
    );
  });

  it('test_aceita_o_texto_real_de_timeout_da_api_quando_avaliado', () => {
    expect(
      ehTextoSeguroParaUsuario('Tempo de processamento excedido (300s).'),
    ).toBe(true);
  });

  it.each([
    ['nao e string', 123],
    ['e nulo', null],
    ['e indefinido', undefined],
    ['e objeto', { detail: 'oi' }],
    ['e string vazia', ''],
    ['so tem espacos', '   '],
  ])('test_recusa_o_valor_quando_%s', (_rotulo, valor) => {
    expect(ehTextoSeguroParaUsuario(valor)).toBe(false);
  });

  it('test_recusa_o_texto_quando_passa_de_200_caracteres', () => {
    expect(ehTextoSeguroParaUsuario('a'.repeat(201))).toBe(false);
    expect(ehTextoSeguroParaUsuario('a'.repeat(200))).toBe(true);
  });

  it.each([
    '/etc/passwd',
    'C:\\Windows\\System32',
    'Traceback recente',
    'RuntimeError: boom',
    'falhou at app.main',
    'retorno 404 do upstream',
    'retorno 500 do upstream',
  ])('test_recusa_o_texto_quando_parece_tecnico (%s)', (texto) => {
    expect(ehTextoSeguroParaUsuario(texto)).toBe(false);
  });

  it.each([
    'KeyError no dicionario de parametros',
    'ValueError ao converter o parametro',
    'OSError ao abrir o arquivo temporario',
    'FFmpegError durante o processamento',
    'houve uma RuntimeException no worker',
    'Traceback resumido do worker',
  ])(
    'test_recusa_o_texto_quando_traz_nome_de_excecao_sem_dois_pontos (%s)',
    (texto) => {
      /**
       * O contrato da função é rejeitar nome de exceção, com ou sem
       * dois-pontos: `KeyError`, `ValueError` e afins soltos no meio da
       * frase não podem chegar à tela do usuário.
       */
      expect(ehTextoSeguroParaUsuario(texto)).toBe(false);
    },
  );

  it.each([
    'O envio falhou. Tente de novo.',
    'Não foi possível ler o vídeo enviado.',
    'O processamento terminou com erro no seu vídeo.',
    'Houve uma exceção à regra de tamanho para este envio.',
  ])(
    'test_continua_aceitando_o_texto_quando_e_frase_de_usuario_com_a_palavra_erro (%s)',
    (texto) => {
      // O filtro mira nomes de exceção em inglês; "erro"/"exceção" em
      // português são vocabulário normal de mensagem ao usuário.
      expect(ehTextoSeguroParaUsuario(texto)).toBe(true);
    },
  );
});

describe('isApiError', () => {
  it('test_reconhece_o_erro_quando_e_instancia_de_ApiError', () => {
    expect(isApiError(new ApiError({ status: 404, context: 'status' }))).toBe(
      true,
    );
  });

  it.each([[new Error('x')], ['texto'], [null], [undefined], [{ status: 404 }]])(
    'test_nao_reconhece_o_valor_quando_nao_e_ApiError (%s)',
    (valor) => {
      expect(isApiError(valor)).toBe(false);
    },
  );
});
