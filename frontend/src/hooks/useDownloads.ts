import { useMutation, type UseMutationResult } from '@tanstack/react-query';
import { fetchJobArchive, fetchVariationFile } from '../api/jobs.ts';
import { nomeSeguro, salvarBlobComoArquivo } from '../lib/download.ts';

export interface DownloadDeVariacaoInput {
  jobId: string;
  variationId: string;
  /** Posição da variação na lista, usada só no nome do arquivo. */
  indice: number;
}

export function useDownloadDeVariacao(): UseMutationResult<
  void,
  Error,
  DownloadDeVariacaoInput
> {
  return useMutation<void, Error, DownloadDeVariacaoInput>({
    mutationFn: async ({ jobId, variationId, indice }) => {
      const blob = await fetchVariationFile(jobId, variationId);
      const numero = String(indice + 1).padStart(2, '0');
      salvarBlobComoArquivo(
        blob,
        `variacao-${numero}-${nomeSeguro(variationId)}.mp4`,
      );
    },
  });
}

export function useDownloadDoZip(): UseMutationResult<void, Error, string> {
  return useMutation<void, Error, string>({
    mutationFn: async (jobId) => {
      const blob = await fetchJobArchive(jobId);
      salvarBlobComoArquivo(blob, `variacoes-${nomeSeguro(jobId)}.zip`);
    },
  });
}
