import { useEffect, useRef } from 'react';
import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { fetchJob } from '../api/jobs.ts';
import { isTerminalStatus, type Job } from '../api/types.ts';
import { calcularIntervaloDePolling } from '../lib/polling.ts';

export function chaveDoJob(jobId: string): readonly [string, string] {
  return ['job', jobId] as const;
}

/**
 * Acompanha um trabalho com polling adaptativo. O polling para
 * sozinho quando o status vira terminal.
 */
export function useJob(jobId: string | null): UseQueryResult<Job, Error> {
  const inicioDoAcompanhamento = useRef<number>(Date.now());

  useEffect(() => {
    inicioDoAcompanhamento.current = Date.now();
  }, [jobId]);

  return useQuery<Job, Error>({
    queryKey: jobId === null ? ['job', 'nenhum'] : chaveDoJob(jobId),
    enabled: jobId !== null,
    queryFn: async ({ signal }) => {
      if (jobId === null) {
        throw new Error('Nenhum trabalho selecionado.');
      }

      return await fetchJob(jobId, signal);
    },
    retry: 2,
    retryDelay: 1_500,
    refetchInterval: (query) => {
      const dados = query.state.data;

      if (dados !== undefined && isTerminalStatus(dados.status)) {
        return false;
      }

      const decorrido = Date.now() - inicioDoAcompanhamento.current;
      return calcularIntervaloDePolling(decorrido);
    },
    // Gerar variações leva minutos e o usuário costuma trocar de aba
    // enquanto espera. Sem isto o progresso congela em segundo plano.
    // O polling se encerra sozinho ao chegar num status terminal.
    refetchIntervalInBackground: true,
  });
}
