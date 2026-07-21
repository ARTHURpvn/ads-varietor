import {
  useMutation,
  useQueryClient,
  type UseMutationResult,
} from '@tanstack/react-query';
import { cancelJob } from '../api/jobs.ts';
import { chaveDoJob } from './useJob.ts';

export function useCancelarJob(
  jobId: string | null,
): UseMutationResult<void, Error, void> {
  const queryClient = useQueryClient();

  return useMutation<void, Error, void>({
    mutationFn: async () => {
      if (jobId === null) {
        throw new Error('Nenhum trabalho selecionado.');
      }

      await cancelJob(jobId);
    },
    onSuccess: async () => {
      if (jobId !== null) {
        await queryClient.invalidateQueries({ queryKey: chaveDoJob(jobId) });
      }
    },
  });
}
