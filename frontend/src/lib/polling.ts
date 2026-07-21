/**
 * Intervalo adaptativo de polling:
 * 1s nos primeiros 30s, 3s depois, com teto de 5s.
 */
export const INTERVALO_INICIAL_MS = 1_000;
export const INTERVALO_TARDIO_MS = 3_000;
export const INTERVALO_MAXIMO_MS = 5_000;
export const JANELA_INICIAL_MS = 30_000;

export function calcularIntervaloDePolling(
  msDesdeOInicio: number,
): number {
  const intervalo =
    msDesdeOInicio < JANELA_INICIAL_MS
      ? INTERVALO_INICIAL_MS
      : INTERVALO_TARDIO_MS;

  return Math.min(intervalo, INTERVALO_MAXIMO_MS);
}
