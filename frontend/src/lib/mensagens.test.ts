import { describe, expect, it } from 'vitest';

import type {
  Job,
  JobStatus,
  Variation,
  VariationParams,
  VariationStatus,
} from '../api/types.ts';
import { analisarHashes } from './hash.ts';
import {
  descricaoDoFiltro,
  ehInterrupcaoPorCancelamento,
  mensagemDaVerificacaoDeHashes,
  motivoDaFalha,
  motivoDaFalhaDoJob,
  motivoDaInterrupcao,
  resumoDaVariacao,
  resumoDosParametros,
  rotuloDoStatusDaVariacao,
  rotuloDoStatusDoJob,
  statusExibidoDaVariacao,
} from './mensagens.ts';

function variacao(
  sobrescritas: Partial<Variation> = {},
): Variation {
  return {
    variation_id: 'var-1',
    status: 'failed',
    error: null,
    size_bytes: null,
    md5: null,
    progress: 0,
    params: {
      speed: 1,
      filter_type: 'brightness',
      filter_value: 0.1,
      background_color: '#000000',
      video_scale: 1,
      noise_audio: false,
    },
    ...sobrescritas,
  };
}

function job(sobrescritas: Partial<Job> = {}): Job {
  return {
    job_id: 'job-1',
    status: 'failed',
    num_variations: 1,
    mode: 'full',
    source_md5: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:10Z',
    error: null,
    progress: { total: 1, completed: 0, failed: 1, percent: 100 },
    variations: [],
    ...sobrescritas,
  };
}

describe('rotuloDoStatusDoJob', () => {
  it.each<[JobStatus, string]>([
    ['pending', 'Na fila'],
    ['running', 'Gerando variações'],
    ['completed', 'Concluído'],
    ['failed', 'Não foi possível concluir'],
    ['cancelled', 'Cancelado por você'],
    ['expired', 'Expirado'],
  ])('test_traduz_o_status_do_job_quando_e_%s', (status, esperado) => {
    expect(rotuloDoStatusDoJob(status)).toBe(esperado);
  });

  it('test_fala_em_preparar_copias_quando_o_modo_nao_reprocessa_o_video', () => {
    expect(rotuloDoStatusDoJob('running', 'metadata_only')).toBe(
      'Preparando as cópias',
    );
  });

  it('test_mantem_o_texto_de_geracao_quando_o_modo_reprocessa_o_video', () => {
    expect(rotuloDoStatusDoJob('running', 'full')).toBe('Gerando variações');
  });

  it('test_nenhum_rotulo_expoe_o_termo_tecnico_em_ingles', () => {
    const statuses: JobStatus[] = [
      'pending',
      'running',
      'completed',
      'failed',
      'cancelled',
      'expired',
    ];

    for (const status of statuses) {
      expect(rotuloDoStatusDoJob(status).toLowerCase()).not.toContain(status);
    }
  });
});

describe('rotuloDoStatusDaVariacao', () => {
  it.each<[VariationStatus | 'interrompida', string]>([
    ['pending', 'Na fila'],
    ['running', 'Gerando'],
    ['completed', 'Pronta'],
    ['failed', 'Falhou'],
    ['interrompida', 'Interrompida'],
  ])('test_traduz_o_status_da_variacao_quando_e_%s', (status, esperado) => {
    expect(rotuloDoStatusDaVariacao(status)).toBe(esperado);
  });
});

describe('statusExibidoDaVariacao', () => {
  it.each<JobStatus>(['completed', 'failed', 'cancelled', 'expired'])(
    'test_mostra_interrompida_quando_a_variacao_ficou_na_fila_e_o_job_terminou_como_%s',
    (statusDoJob) => {
      const resultado = statusExibidoDaVariacao(
        variacao({ status: 'pending' }),
        statusDoJob,
      );

      expect(resultado).toBe('interrompida');
    },
  );

  it('test_mostra_interrompida_quando_a_variacao_estava_rodando_e_o_job_foi_cancelado', () => {
    expect(
      statusExibidoDaVariacao(variacao({ status: 'running' }), 'cancelled'),
    ).toBe('interrompida');
  });

  it('test_preserva_o_status_da_variacao_quando_o_job_ainda_esta_rodando', () => {
    expect(
      statusExibidoDaVariacao(variacao({ status: 'pending' }), 'running'),
    ).toBe('pending');
  });

  it('test_preserva_completed_quando_a_variacao_ja_ficou_pronta_num_job_encerrado', () => {
    expect(
      statusExibidoDaVariacao(variacao({ status: 'completed' }), 'cancelled'),
    ).toBe('completed');
  });

  it('test_preserva_failed_quando_a_variacao_falhou_num_job_encerrado', () => {
    expect(
      statusExibidoDaVariacao(variacao({ status: 'failed' }), 'expired'),
    ).toBe('failed');
  });

  it('test_mostra_interrompida_quando_o_cancelamento_pegou_a_renderizacao_sem_detalhe_de_erro', () => {
    expect(
      statusExibidoDaVariacao(
        variacao({ status: 'failed', error: null }),
        'cancelled',
      ),
    ).toBe('interrompida');
  });

  it('test_mostra_interrompida_quando_o_erro_so_fala_do_proprio_cancelamento', () => {
    expect(
      statusExibidoDaVariacao(
        variacao({ status: 'failed', error: 'Falha ao renderizar: cancelled' }),
        'cancelled',
      ),
    ).toBe('interrompida');
  });

  it('test_preserva_failed_quando_a_falha_e_real_mesmo_com_o_job_cancelado', () => {
    /** O disco encheu antes de o usuário cancelar: isso é falha mesmo. */
    expect(
      statusExibidoDaVariacao(
        variacao({ status: 'failed', error: 'Falha ao renderizar: ENOSPC' }),
        'cancelled',
      ),
    ).toBe('failed');
  });
});

describe('ehInterrupcaoPorCancelamento', () => {
  it('test_reconhece_a_interrupcao_quando_o_job_foi_cancelado_e_nao_ha_erro', () => {
    expect(
      ehInterrupcaoPorCancelamento(
        variacao({ status: 'failed', error: '   ' }),
        'cancelled',
      ),
    ).toBe(true);
  });

  it('test_nega_a_interrupcao_quando_o_erro_descreve_um_problema_real', () => {
    expect(
      ehInterrupcaoPorCancelamento(
        variacao({ status: 'failed', error: 'Falha ao renderizar: ENOSPC' }),
        'cancelled',
      ),
    ).toBe(false);
  });

  it('test_nega_a_interrupcao_quando_o_job_nao_foi_cancelado', () => {
    expect(
      ehInterrupcaoPorCancelamento(
        variacao({ status: 'failed', error: null }),
        'failed',
      ),
    ).toBe(false);
  });

  it('test_nega_a_interrupcao_quando_a_variacao_ficou_pronta', () => {
    expect(
      ehInterrupcaoPorCancelamento(
        variacao({ status: 'completed', error: null }),
        'cancelled',
      ),
    ).toBe(false);
  });
});

describe('motivoDaFalha', () => {
  it('test_reconhece_timeout_quando_a_api_manda_o_texto_real_em_portugues', () => {
    /** Regressão: só palavras em inglês eram reconhecidas. */
    const resultado = motivoDaFalha(
      variacao({ error: 'Tempo de processamento excedido (300s).' }),
    );

    expect(resultado).toBe(
      'A geração demorou mais do que o permitido e foi interrompida.',
    );
  });

  it('test_reconhece_timeout_quando_o_ffmpeg_reporta_em_ingles', () => {
    expect(
      motivoDaFalha(
        variacao({ error: 'Falha ao renderizar: Operation timed out' }),
      ),
    ).toBe('A geração demorou mais do que o permitido e foi interrompida.');
  });

  it('test_avisa_sobre_disco_cheio_quando_o_erro_menciona_enospc', () => {
    expect(
      motivoDaFalha(
        variacao({ error: 'Falha ao renderizar: ENOSPC write failed' }),
      ),
    ).toBe('O servidor ficou sem espaço enquanto gerava esta variação.');
  });

  it('test_avisa_sobre_formato_ilegivel_quando_o_ffmpeg_reclama_de_invalid_data', () => {
    expect(
      motivoDaFalha(
        variacao({
          error: 'Falha ao renderizar: Invalid data found when processing input',
        }),
      ),
    ).toBe('O formato deste vídeo não pôde ser lido nesta variação.');
  });

  it('test_avisa_sobre_render_quando_o_erro_e_apenas_o_prefixo_da_api', () => {
    expect(
      motivoDaFalha(variacao({ error: 'Falha ao renderizar: exit status 1' })),
    ).toBe('O servidor não conseguiu renderizar esta variação.');
  });

  it('test_usa_o_motivo_generico_quando_o_erro_e_nulo', () => {
    expect(motivoDaFalha(variacao({ error: null }))).toBe(
      'Não foi possível gerar esta variação. Tente gerar novamente.',
    );
  });

  it('test_usa_o_motivo_generico_quando_o_erro_e_string_vazia', () => {
    expect(motivoDaFalha(variacao({ error: '' }))).toBe(
      'Não foi possível gerar esta variação. Tente gerar novamente.',
    );
  });

  it('test_nunca_expoe_path_nem_stack_quando_o_erro_traz_detalhe_tecnico', () => {
    const tecnico =
      'Traceback (most recent call last): File "/srv/app/core/ffmpeg.py", line 88';
    const resultado = motivoDaFalha(variacao({ error: tecnico }));

    expect(resultado).not.toContain('/srv');
    expect(resultado).not.toContain('Traceback');
    expect(resultado).toBe(
      'Não foi possível gerar esta variação. Tente gerar novamente.',
    );
  });
});

describe('motivoDaInterrupcao', () => {
  it('test_culpa_o_cancelamento_quando_o_job_foi_cancelado', () => {
    expect(motivoDaInterrupcao('cancelled')).toBe(
      'Esta variação não ficou pronta porque você cancelou a geração.',
    );
  });

  it('test_culpa_a_expiracao_quando_o_job_expirou', () => {
    expect(motivoDaInterrupcao('expired')).toBe(
      'Esta variação não ficou pronta antes de o trabalho expirar.',
    );
  });

  it.each<JobStatus>(['failed', 'completed', 'pending', 'running'])(
    'test_usa_texto_neutro_quando_o_job_terminou_como_%s',
    (status) => {
      expect(motivoDaInterrupcao(status)).toBe(
        'Esta variação não chegou a ser gerada.',
      );
    },
  );
});

describe('motivoDaFalhaDoJob', () => {
  it('test_mostra_o_texto_da_api_quando_ele_e_seguro_para_o_usuario', () => {
    expect(
      motivoDaFalhaDoJob(job({ error: 'O vídeo enviado não pôde ser lido.' })),
    ).toBe('O vídeo enviado não pôde ser lido.');
  });

  it('test_troca_por_texto_generico_quando_o_erro_traz_path_de_sistema', () => {
    expect(
      motivoDaFalhaDoJob(job({ error: '/srv/storage/jobs/abc/input.mp4' })),
    ).toBe('Não conseguimos processar este vídeo.');
  });

  it('test_troca_por_texto_generico_quando_o_erro_e_nulo', () => {
    expect(motivoDaFalhaDoJob(job({ error: null }))).toBe(
      'Não conseguimos processar este vídeo.',
    );
  });

  it('test_troca_por_texto_generico_quando_o_erro_traz_nome_de_excecao', () => {
    expect(
      motivoDaFalhaDoJob(job({ error: 'InvalidVideoException ao abrir' })),
    ).toBe('Não conseguimos processar este vídeo.');
  });
});

describe('resumoDosParametros', () => {
  it('test_descreve_todos_os_parametros_quando_nao_ha_ruido_no_audio', () => {
    const resultado = resumoDosParametros(
      variacao({
        params: {
          speed: 1.05,
          filter_type: 'brightness',
          filter_value: 0.2,
          background_color: '#112233',
          video_scale: 0.98,
          noise_audio: false,
        },
      }),
    );

    expect(resultado).toBe(
      'velocidade 1.05x · brilho 0.20 · escala 0.98x · fundo #112233',
    );
  });

  it.each<[string, string]>([
    ['brightness', 'brilho'],
    ['contrast', 'contraste'],
    ['saturate', 'saturação'],
    ['hue', 'matiz'],
  ])(
    'test_traduz_o_filtro_%s_para_o_termo_em_portugues',
    (tipo, traducao) => {
      const resultado = resumoDosParametros(
        variacao({
          params: {
            speed: 1,
            filter_type: tipo,
            filter_value: 1.08,
            background_color: '#000000',
            video_scale: 1,
            noise_audio: false,
          },
        }),
      );

      expect(resultado).toContain(`${traducao} 1.08`);
      // "contraste" contém "contrast": o que não pode aparecer é o enum
      // cru no lugar do rótulo, não a substring dentro da tradução.
      expect(resultado).not.toContain(`${tipo} 1.08`);
    },
  );

  it('test_omite_o_filtro_quando_a_api_manda_none', () => {
    const resultado = resumoDosParametros(
      variacao({
        params: {
          speed: 1,
          filter_type: 'none',
          filter_value: 1,
          background_color: '#000000',
          video_scale: 1,
          noise_audio: false,
        },
      }),
    );

    expect(resultado).toBe(
      'velocidade 1.00x · escala 1.00x · fundo #000000',
    );
    expect(resultado).not.toContain('none');
  });

  it('test_omite_o_filtro_quando_o_tipo_e_desconhecido', () => {
    /** Nunca despejar o enum cru da API na interface. */
    const resultado = resumoDosParametros(
      variacao({
        params: {
          speed: 1,
          filter_type: 'gblur',
          filter_value: 2,
          background_color: '#000000',
          video_scale: 1,
          noise_audio: false,
        },
      }),
    );

    expect(resultado).not.toContain('gblur');
  });

  it('test_acrescenta_ruido_no_audio_quando_o_parametro_esta_ligado', () => {
    const resultado = resumoDosParametros(
      variacao({
        params: {
          speed: 1,
          filter_type: 'brightness',
          filter_value: 0,
          background_color: '#000000',
          video_scale: 1,
          noise_audio: true,
        },
      }),
    );

    expect(resultado.endsWith('· ruído no áudio')).toBe(true);
  });
});

describe('descricaoDoFiltro', () => {
  function params(tipo: string, valor = 1.03): VariationParams {
    return {
      speed: 1,
      filter_type: tipo,
      filter_value: valor,
      background_color: '#000000',
      video_scale: 1,
      noise_audio: false,
    };
  }

  it('test_descreve_o_efeito_quando_o_tipo_e_conhecido', () => {
    expect(descricaoDoFiltro(params('hue'))).toBe('matiz 1.03');
  });

  it('test_nao_descreve_nada_quando_nao_ha_efeito_de_cor', () => {
    expect(descricaoDoFiltro(params('none'))).toBeNull();
  });

  it('test_nao_descreve_nada_quando_o_tipo_e_desconhecido', () => {
    expect(descricaoDoFiltro(params('unsharp'))).toBeNull();
  });
});

describe('resumoDaVariacao', () => {
  it('test_descreve_os_parametros_quando_o_modo_reprocessa_o_video', () => {
    expect(resumoDaVariacao(variacao(), 'full')).toBe(
      resumoDosParametros(variacao()),
    );
  });

  it('test_omite_os_parametros_quando_o_modo_nao_reprocessa_o_video', () => {
    const resultado = resumoDaVariacao(variacao(), 'metadata_only');

    expect(resultado).toBe(
      'Imagem e som idênticos ao original — só a identificação interna mudou.',
    );
    expect(resultado).not.toContain('velocidade');
    expect(resultado).not.toContain('escala');
    expect(resultado).not.toContain('fundo');
  });
});

describe('mensagemDaVerificacaoDeHashes', () => {
  it('test_confirma_a_unicidade_quando_todos_os_hashes_sao_distintos', () => {
    const analise = analisarHashes(['aaa', 'bbb', 'ccc'], 'zzz');

    expect(mensagemDaVerificacaoDeHashes(analise, 'full')).toBe(
      'Conferimos 3 identificações: nenhuma se repete e nenhuma é igual à ' +
        'do arquivo original.',
    );
  });

  it('test_usa_o_singular_quando_ha_um_unico_hash_conferido', () => {
    const analise = analisarHashes(['aaa'], 'zzz');

    expect(mensagemDaVerificacaoDeHashes(analise, 'full')).toContain(
      'Conferimos 1 identificação:',
    );
  });

  it('test_avisa_sobre_repeticao_quando_dois_arquivos_tem_o_mesmo_hash', () => {
    const analise = analisarHashes(['aaa', 'aaa'], 'zzz');
    const resultado = mensagemDaVerificacaoDeHashes(analise, 'full');

    expect(resultado).toContain('1 identificação aparece em mais de um arquivo.');
    expect(resultado).toContain('Gere as variações de novo.');
  });

  it('test_avisa_quando_algum_arquivo_ficou_igual_ao_original', () => {
    const analise = analisarHashes(['aaa', 'zzz'], 'zzz');

    expect(mensagemDaVerificacaoDeHashes(analise, 'metadata_only')).toContain(
      '1 arquivo ficou idêntico ao original.',
    );
  });

  it('test_usa_o_termo_copias_quando_o_modo_nao_reprocessa_o_video', () => {
    const analise = analisarHashes(['aaa', 'aaa'], 'zzz');

    expect(mensagemDaVerificacaoDeHashes(analise, 'metadata_only')).toContain(
      'Gere as cópias de novo.',
    );
  });

  it('test_menciona_os_arquivos_sem_identificacao_registrada', () => {
    const analise = analisarHashes(['aaa', null], 'zzz');

    expect(mensagemDaVerificacaoDeHashes(analise, 'full')).toContain(
      '1 arquivo ainda não tem identificação registrada.',
    );
  });
});
