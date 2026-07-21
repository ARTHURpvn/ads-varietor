import { useCallback, useState } from 'react';

const CHAVE_ARMAZENAMENTO = 'video-variations:ultimo-job-id';

function lerJobIdSalvo(): string | null {
  try {
    const valor = window.localStorage.getItem(CHAVE_ARMAZENAMENTO);
    return valor !== null && valor.length > 0 ? valor : null;
  } catch {
    // localStorage indisponível (modo privado, por exemplo).
    return null;
  }
}

export interface JobArmazenado {
  jobIdSalvo: string | null;
  salvarJobId: (jobId: string) => void;
  limparJobId: () => void;
}

/** Persiste o job_id para permitir retomar o trabalho ao reabrir a página. */
export function useJobArmazenado(): JobArmazenado {
  const [jobIdSalvo, setJobIdSalvo] = useState<string | null>(lerJobIdSalvo);

  const salvarJobId = useCallback((jobId: string): void => {
    setJobIdSalvo(jobId);

    try {
      window.localStorage.setItem(CHAVE_ARMAZENAMENTO, jobId);
    } catch {
      // Sem persistência: o fluxo da sessão atual continua funcionando.
    }
  }, []);

  const limparJobId = useCallback((): void => {
    setJobIdSalvo(null);

    try {
      window.localStorage.removeItem(CHAVE_ARMAZENAMENTO);
    } catch {
      // Nada a fazer.
    }
  }, []);

  return { jobIdSalvo, salvarJobId, limparJobId };
}
