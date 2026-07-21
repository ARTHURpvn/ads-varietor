import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { fetchHealth } from '../api/jobs.ts';
import type { HealthStatus } from '../api/types.ts';

const INTERVALO_DE_CHECAGEM_MS = 60_000;

/**
 * Consulta a saúde do serviço na tela de envio. Quando o FFmpeg está
 * fora do ar a API responde `degraded` — avisar antes evita o usuário
 * esperar minutos por um trabalho que já nasce condenado.
 *
 * A falha da própria checagem é silenciosa: ela nunca deve bloquear o
 * envio nem competir com o erro real do upload.
 */
export function useSaudeDoServico(): UseQueryResult<HealthStatus, Error> {
  return useQuery<HealthStatus, Error>({
    queryKey: ['saude-do-servico'],
    queryFn: async () => await fetchHealth(),
    retry: false,
    staleTime: INTERVALO_DE_CHECAGEM_MS,
    refetchInterval: INTERVALO_DE_CHECAGEM_MS,
  });
}
