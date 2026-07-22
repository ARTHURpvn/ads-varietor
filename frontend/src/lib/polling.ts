/**
 * Intervalo adaptativo de polling. A frequência cai conforme o trabalho se
 * alonga: 1s nos primeiros 30s, 2s até 2min e 3s daí em diante.
 *
 * Os intervalos tardios são mais curtos do que seriam necessários só para
 * saber quantos arquivos ficaram prontos. Eles existem porque a barra mostra
 * o andamento por dentro de cada variação: com 5s entre respostas, ela
 * andaria em degraus visíveis mesmo com a transição suavizando.
 */
export const INTERVALO_INICIAL_MS = 1_000;
export const INTERVALO_TARDIO_MS = 2_000;
export const INTERVALO_MAXIMO_MS = 3_000;
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
