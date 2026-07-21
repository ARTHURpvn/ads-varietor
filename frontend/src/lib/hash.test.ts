import { describe, expect, it } from 'vitest';

import { analisarHashes, encurtarHash, normalizarHash } from './hash.ts';

const HASH_A = '0123456789abcdef0123456789abcdef';
const HASH_B = 'fedcba9876543210fedcba9876543210';
const HASH_ORIGEM = 'aaaaaaaabbbbbbbbccccccccdddddddd';

describe('normalizarHash', () => {
  it('test_devolve_nulo_quando_o_hash_e_nulo', () => {
    expect(normalizarHash(null)).toBeNull();
  });

  it('test_devolve_nulo_quando_o_hash_nao_veio_na_resposta', () => {
    expect(normalizarHash(undefined)).toBeNull();
  });

  it('test_devolve_nulo_quando_o_hash_e_so_espaco_em_branco', () => {
    expect(normalizarHash('   ')).toBeNull();
  });

  it('test_baixa_a_caixa_e_apara_espacos_quando_o_hash_e_valido', () => {
    expect(normalizarHash(`  ${HASH_A.toUpperCase()} `)).toBe(HASH_A);
  });
});

describe('encurtarHash', () => {
  it('test_mostra_as_duas_pontas_quando_o_hash_tem_32_caracteres', () => {
    expect(encurtarHash(HASH_A)).toBe('01234567…89abcdef');
  });

  it('test_devolve_o_hash_inteiro_quando_ele_ja_cabe_na_tela', () => {
    expect(encurtarHash('abc123')).toBe('abc123');
  });

  it('test_respeita_a_quantidade_de_caracteres_pedida', () => {
    expect(encurtarHash(HASH_A, 4)).toBe('0123…cdef');
  });

  it('test_devolve_o_hash_inteiro_quando_a_quantidade_pedida_e_zero', () => {
    expect(encurtarHash(HASH_A, 0)).toBe(HASH_A);
  });
});

describe('analisarHashes', () => {
  it('test_aprova_quando_todos_os_hashes_sao_distintos_e_diferentes_do_original', () => {
    const analise = analisarHashes([HASH_A, HASH_B], HASH_ORIGEM);

    expect(analise.tudoDistinto).toBe(true);
    expect(analise.comHash).toBe(2);
    expect(analise.semHash).toBe(0);
    expect(analise.duplicados).toEqual([]);
    expect(analise.repetemOOriginal).toBe(0);
  });

  it('test_aponta_o_duplicado_quando_dois_arquivos_tem_o_mesmo_hash', () => {
    const analise = analisarHashes([HASH_A, HASH_B, HASH_A], HASH_ORIGEM);

    expect(analise.tudoDistinto).toBe(false);
    expect(analise.duplicados).toEqual([HASH_A]);
  });

  it('test_trata_como_duplicado_quando_o_mesmo_hash_vem_em_caixas_diferentes', () => {
    const analise = analisarHashes(
      [HASH_A, HASH_A.toUpperCase()],
      HASH_ORIGEM,
    );

    expect(analise.duplicados).toEqual([HASH_A]);
  });

  it('test_acusa_quando_um_arquivo_ficou_igual_ao_original', () => {
    const analise = analisarHashes([HASH_A, HASH_ORIGEM], HASH_ORIGEM);

    expect(analise.repetemOOriginal).toBe(1);
    expect(analise.tudoDistinto).toBe(false);
  });

  it('test_conta_a_parte_os_arquivos_sem_hash_em_vez_de_trata_los_como_iguais', () => {
    const analise = analisarHashes([null, null, HASH_A], HASH_ORIGEM);

    expect(analise.semHash).toBe(2);
    expect(analise.comHash).toBe(1);
    expect(analise.duplicados).toEqual([]);
    expect(analise.tudoDistinto).toBe(true);
  });

  it('test_nao_afirma_unicidade_quando_nenhum_hash_e_conhecido', () => {
    const analise = analisarHashes([null, null], HASH_ORIGEM);

    expect(analise.comHash).toBe(0);
    expect(analise.tudoDistinto).toBe(false);
  });

  it('test_ignora_a_comparacao_com_a_origem_quando_o_hash_de_origem_e_nulo', () => {
    const analise = analisarHashes([HASH_A, HASH_B], null);

    expect(analise.repetemOOriginal).toBe(0);
    expect(analise.tudoDistinto).toBe(true);
  });

  it('test_devolve_analise_vazia_quando_nao_ha_variacao_alguma', () => {
    const analise = analisarHashes([], HASH_ORIGEM);

    expect(analise.comHash).toBe(0);
    expect(analise.semHash).toBe(0);
    expect(analise.tudoDistinto).toBe(false);
  });
});
