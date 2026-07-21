import { describe, expect, it } from 'vitest';

import {
  ACCEPT_ATTRIBUTE,
  formatarTamanho,
  validarArquivoDeVideo,
} from './videoFile.ts';

const MENSAGEM_RECUSA = 'Envie um arquivo de vídeo (MP4, MOV ou WebM).';

function arquivo(nome: string, tipo: string, bytes = 10): File {
  return new File([new Uint8Array(bytes)], nome, { type: tipo });
}

describe('validarArquivoDeVideo — aceitação por MIME', () => {
  it('test_aceita_o_arquivo_quando_o_mime_e_video_mp4', () => {
    const resultado = validarArquivoDeVideo(arquivo('clipe.bin', 'video/mp4'));

    expect(resultado.valido).toBe(true);
  });

  it('test_aceita_o_arquivo_quando_o_mime_e_quicktime_do_mov', () => {
    const resultado = validarArquivoDeVideo(
      arquivo('clipe.bin', 'video/quicktime'),
    );

    expect(resultado.valido).toBe(true);
  });

  it('test_aceita_o_arquivo_quando_o_mime_e_video_webm', () => {
    const resultado = validarArquivoDeVideo(arquivo('clipe.bin', 'video/webm'));

    expect(resultado.valido).toBe(true);
  });

  it('test_aceita_o_arquivo_quando_o_mime_vem_em_caixa_alta', () => {
    const resultado = validarArquivoDeVideo(arquivo('clipe.bin', 'VIDEO/MP4'));

    expect(resultado.valido).toBe(true);
  });
});

describe('validarArquivoDeVideo — aceitação por extensão', () => {
  it.each(['filme.mp4', 'filme.mov', 'filme.webm', 'filme.m4v'])(
    'test_aceita_o_arquivo_quando_a_extensao_e_de_video (%s)',
    (nome) => {
      const resultado = validarArquivoDeVideo(arquivo(nome, ''));

      expect(resultado.valido).toBe(true);
    },
  );

  it('test_aceita_o_arquivo_quando_a_extensao_esta_em_caixa_alta', () => {
    const resultado = validarArquivoDeVideo(arquivo('FILME.MOV', ''));

    expect(resultado.valido).toBe(true);
  });

  it('test_devolve_o_mesmo_arquivo_quando_a_validacao_passa', () => {
    const original = arquivo('filme.mp4', 'video/mp4');
    const resultado = validarArquivoDeVideo(original);

    expect(resultado).toEqual({ valido: true, arquivo: original });
  });
});

describe('validarArquivoDeVideo — recusa', () => {
  it('test_recusa_com_a_mensagem_padrao_quando_o_arquivo_e_pdf', () => {
    const resultado = validarArquivoDeVideo(
      arquivo('contrato.pdf', 'application/pdf'),
    );

    expect(resultado).toEqual({ valido: false, mensagem: MENSAGEM_RECUSA });
  });

  it.each([
    ['imagem.png', 'image/png'],
    ['musica.mp3', 'audio/mpeg'],
    ['planilha.xlsx', 'application/vnd.ms-excel'],
    ['script.sh', 'text/x-shellscript'],
    ['sem-extensao', ''],
    ['fake.mp4.exe', 'application/octet-stream'],
  ])(
    'test_recusa_o_arquivo_quando_nao_e_video (%s)',
    (nome, tipo) => {
      const resultado = validarArquivoDeVideo(arquivo(nome, tipo));

      expect(resultado.valido).toBe(false);
      if (!resultado.valido) {
        expect(resultado.mensagem).toBe(MENSAGEM_RECUSA);
      }
    },
  );

  it('test_recusa_com_mensagem_propria_quando_o_arquivo_esta_vazio', () => {
    const resultado = validarArquivoDeVideo(arquivo('vazio.mp4', 'video/mp4', 0));

    expect(resultado).toEqual({
      valido: false,
      mensagem: 'Este arquivo está vazio. Escolha outro vídeo.',
    });
  });
});

describe('ACCEPT_ATTRIBUTE', () => {
  it('test_lista_mimes_e_extensoes_quando_usado_no_input_file', () => {
    const partes = ACCEPT_ATTRIBUTE.split(',');

    expect(partes).toContain('video/mp4');
    expect(partes).toContain('video/quicktime');
    expect(partes).toContain('video/webm');
    expect(partes).toContain('.mp4');
    expect(partes).toContain('.mov');
    expect(partes).toContain('.webm');
  });
});

describe('formatarTamanho', () => {
  it.each([
    [0, '0 B'],
    [1, '1 B'],
    [1023, '1023 B'],
  ])('test_mostra_bytes_crus_quando_abaixo_de_1_kb (%i)', (bytes, esperado) => {
    expect(formatarTamanho(bytes)).toBe(esperado);
  });

  it('test_mostra_em_kb_quando_o_tamanho_atinge_1024_bytes', () => {
    expect(formatarTamanho(1024)).toBe('1.0 KB');
  });

  it('test_usa_uma_casa_decimal_quando_o_valor_e_menor_que_dez', () => {
    expect(formatarTamanho(1536)).toBe('1.5 KB');
  });

  it('test_omite_a_casa_decimal_quando_o_valor_chega_a_dez', () => {
    expect(formatarTamanho(10 * 1024)).toBe('10 KB');
  });

  it('test_sobe_para_mb_quando_passa_de_1024_kb', () => {
    expect(formatarTamanho(5 * 1024 * 1024)).toBe('5.0 MB');
  });

  it('test_sobe_para_gb_quando_passa_de_1024_mb', () => {
    expect(formatarTamanho(3 * 1024 ** 3)).toBe('3.0 GB');
  });

  it('test_permanece_em_gb_quando_o_tamanho_passa_de_1024_gb', () => {
    expect(formatarTamanho(2 * 1024 ** 4)).toBe('2048 GB');
  });
});
