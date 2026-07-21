import { useMutation, type UseMutationResult } from '@tanstack/react-query';
import { createJob, type CreateJobInput } from '../api/jobs.ts';
import type { CreatedJob } from '../api/types.ts';

export function useCriarJob(
  aoCriar: (job: CreatedJob) => void,
): UseMutationResult<CreatedJob, Error, CreateJobInput> {
  return useMutation<CreatedJob, Error, CreateJobInput>({
    mutationFn: createJob,
    onSuccess: aoCriar,
  });
}
