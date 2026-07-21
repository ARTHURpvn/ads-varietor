import { describe, expect, it } from 'vitest';

import type { ProcessingMode } from '../api/types.ts';
import {
  MODOS,
  MODO_PADRAO,
  descricaoDoModo,
  rotuloDaSaida,
  rotuloDasSaidas,
  tituloDaSaida,
} from './modos.ts';

describe('MODOS', () => {
  it('test_oferece_os_dois_modos_da_api', () => {
    expect(MODOS.map((opcao) => opcao.modo)).toEqual([
      'full',
      'metadata_only',
    ]);
  });

  it('test_comeca_pelo_modo_padrao', () => {
    expect(MODOS[0]?.modo).toBe(MODO_PADRAO);
  });

  it('test_marca_como_rapido_apenas_o_modo_que_nao_reprocessa_o_video', () => {
    expect(descricaoDoModo('metadata_only').rapido).toBe(true);
    expect(descricaoDoModo('full').rapido).toBe(false);
  });

  it('test_nenhum_texto_expoe_jargao_tecnico_para_o_usuario', () => {
    const proibidos = [
      'reencod',
      'stream',
      'ffmpeg',
      'md5',
      'hash',
      'metadata_only',
      'codec',
    ];

    for (const opcao of MODOS) {
      const texto =
        `${opcao.titulo} ${opcao.descricao} ${opcao.etiquetaDeTempo}`.toLowerCase();

      for (const termo of proibidos) {
        expect(texto).not.toContain(termo);
      }
    }
  });

  it('test_cada_opcao_declara_o_tempo_esperado', () => {
    for (const opcao of MODOS) {
      expect(opcao.etiquetaDeTempo.trim().length).toBeGreaterThan(0);
    }
  });
});

describe('descricaoDoModo', () => {
  it.each<ProcessingMode>(['full', 'metadata_only'])(
    'test_devolve_a_descricao_correspondente_quando_o_modo_e_%s',
    (modo) => {
      expect(descricaoDoModo(modo).modo).toBe(modo);
    },
  );
});

describe('rótulos das saídas', () => {
  it('test_chama_de_variacoes_quando_o_video_e_reprocessado', () => {
    expect(rotuloDasSaidas('full')).toBe('variações');
    expect(rotuloDaSaida('full')).toBe('variação');
    expect(tituloDaSaida('full')).toBe('Variação');
  });

  it('test_chama_de_copias_quando_a_imagem_nao_muda', () => {
    expect(rotuloDasSaidas('metadata_only')).toBe('cópias');
    expect(rotuloDaSaida('metadata_only')).toBe('cópia');
    expect(tituloDaSaida('metadata_only')).toBe('Cópia');
  });
});
