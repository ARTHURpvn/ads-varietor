/**
 * Intervalo adaptativo de polling. A frequência cai conforme o
 * trabalho se alonga: 1s nos primeiros 30s, 3s até 2min e 5s daí em
 * diante. Um job de 50 variações demora, e não faz sentido bater na
 * API a cada segundo durante minutos.
 */
export const INTERVALO_INICIAL_MS = 1_000;
export const INTERVALO_TARDIO_MS = 3_000;
export const INTERVALO_MAXIMO_MS = 5_000;
export const JANELA_INICIAL_MS = 30_000;
export const JANELA_TARDIA_MS = 120_000;

export function calcularIntervaloDePolling(
  msDesdeOInicio: number,
): number {
  if (msDesdeOInicio < JANELA_INICIAL_MS) {
    return INTERVALO_INICIAL_MS;
  }

  if (msDesdeOInicio < JANELA_TARDIA_MS) {
    return INTERVALO_TARDIO_MS;
  }

  return INTERVALO_MAXIMO_MS;
}
