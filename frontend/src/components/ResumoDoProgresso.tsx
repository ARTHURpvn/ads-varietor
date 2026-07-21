import type { ReactElement } from 'react';
import type { Job } from '../api/types.ts';
import { rotuloDoStatusDoJob } from '../lib/mensagens.ts';
import { BarraDeProgresso } from './BarraDeProgresso.tsx';

interface ResumoDoProgressoProps {
  job: Job;
}

/** Barra + contador "X de N concluídas", anunciados por leitor de tela. */
export function ResumoDoProgresso({ job }: ResumoDoProgressoProps): ReactElement {
  const total = job.progress.total > 0 ? job.progress.total : job.num_variations;
  const contador = `${job.progress.completed} de ${total} concluídas`;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-sm font-semibold text-texto">
          {rotuloDoStatusDoJob(job.status)}
        </p>

        <p aria-live="polite" className="text-sm text-texto-suave">
          {contador}
          {job.progress.failed > 0
            ? ` · ${job.progress.failed} com falha`
            : ''}
        </p>
      </div>

      <BarraDeProgresso
        concluidas={job.progress.completed}
        total={total}
        rotulo={contador}
      />
    </div>
  );
}
