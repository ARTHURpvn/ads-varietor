import { describe, expect, it } from 'vitest';

import {
  calcularIntervaloDePolling,
  INTERVALO_INICIAL_MS,
  INTERVALO_MAXIMO_MS,
  INTERVALO_TARDIO_MS,
  JANELA_INICIAL_MS,
  JANELA_TARDIA_MS,
} from './polling.ts';

describe('calcularIntervaloDePolling', () => {
  it('test_usa_intervalo_de_1s_quando_o_trabalho_acabou_de_comecar', () => {
    expect(calcularIntervaloDePolling(0)).toBe(1_000);
  });

  it('test_mantem_1s_quando_esta_no_ultimo_ms_da_janela_inicial', () => {
    expect(calcularIntervaloDePolling(29_999)).toBe(1_000);
  });

  it('test_sobe_para_3s_quando_cruza_exatamente_30s', () => {
    expect(calcularIntervaloDePolling(30_000)).toBe(3_000);
  });

  it('test_mantem_3s_quando_esta_no_ultimo_ms_da_janela_tardia', () => {
    expect(calcularIntervaloDePolling(119_999)).toBe(3_000);
  });

  it('test_sobe_para_5s_quando_cruza_exatamente_120s', () => {
    /** Regressão: o teto de 5s já foi código morto e nunca era atingido. */
    expect(calcularIntervaloDePolling(120_000)).toBe(5_000);
  });

  it('test_permanece_no_teto_de_5s_quando_o_trabalho_passa_de_10min', () => {
    expect(calcularIntervaloDePolling(600_000)).toBe(5_000);
  });

  it('test_o_teto_de_5s_e_alcancavel_quando_o_tempo_cresce_indefinidamente', () => {
    const intervalosVistos = new Set(
      [0, 15_000, 45_000, 200_000, 3_600_000].map(calcularIntervaloDePolling),
    );

    expect(intervalosVistos).toEqual(new Set([1_000, 3_000, 5_000]));
  });

  it('test_a_escalada_nunca_diminui_quando_o_tempo_avanca', () => {
    const amostras = Array.from({ length: 200 }, (_, i) => i * 1_500);
    const intervalos = amostras.map(calcularIntervaloDePolling);

    for (let i = 1; i < intervalos.length; i += 1) {
      expect(intervalos[i] ?? 0).toBeGreaterThanOrEqual(intervalos[i - 1] ?? 0);
    }
  });

  it('test_trata_tempo_negativo_como_inicio_quando_o_relogio_regride', () => {
    expect(calcularIntervaloDePolling(-1)).toBe(INTERVALO_INICIAL_MS);
  });

  it('test_as_constantes_publicas_batem_com_as_fronteiras_usadas', () => {
    expect(INTERVALO_INICIAL_MS).toBe(1_000);
    expect(INTERVALO_TARDIO_MS).toBe(3_000);
    expect(INTERVALO_MAXIMO_MS).toBe(5_000);
    expect(calcularIntervaloDePolling(JANELA_INICIAL_MS)).toBe(
      INTERVALO_TARDIO_MS,
    );
    expect(calcularIntervaloDePolling(JANELA_TARDIA_MS)).toBe(
      INTERVALO_MAXIMO_MS,
    );
  });
});
