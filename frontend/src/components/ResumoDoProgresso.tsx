import type { ReactElement } from 'react';
import { isTerminalStatus, type Job } from '../api/types.ts';
import { rotuloDoStatusDoJob } from '../lib/mensagens.ts';
import { BarraDeProgresso } from './BarraDeProgresso.tsx';
import { TiraDeVariacoes } from './TiraDeVariacoes.tsx';

interface ResumoDoProgressoProps {
  job: Job;
  /**
   * A barra só ajuda quando a espera é longa. Em trabalhos que terminam
   * em menos de um segundo ela pisca sem informar nada.
   */
  mostrarBarra?: boolean;
}

/**
 * Painel de andamento: percentual grande, contadores, barra e a tira com
 * uma célula por saída. Tudo o que a tira mostra em cor está também em
 * texto, no bloco anunciado por `aria-live`.
 */
export function ResumoDoProgresso({
  job,
  mostrarBarra = true,
}: ResumoDoProgressoProps): ReactElement {
  const total =
    job.progress.total > 0 ? job.progress.total : job.num_variations;
  const contador = `${job.progress.completed} de ${total} concluídas`;
  const percentual =
    total > 0 ? Math.min(100, Math.round((job.progress.completed / total) * 100))
    : 0;
  const emAndamento = !isTerminalStatus(job.status);

  return (
    <div
      className="flex flex-col gap-4 rounded-xl border border-borda
                 bg-superficie p-4 shadow-[var(--sombra-cartao)] sm:p-5"
    >
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <div className="flex items-end gap-3">
          <p className="font-mono text-display font-semibold text-texto">
            {percentual}
            <span className="ml-1 text-titulo text-texto-fraco">%</span>
          </p>

          <div className="pb-1">
            <p className="font-mono text-selo uppercase text-texto-fraco">
              Situação
            </p>
            <p className="text-nota font-semibold text-texto">
              {rotuloDoStatusDoJob(job.status, job.mode)}
            </p>
          </div>
        </div>

        <p
          aria-live="polite"
          className="font-mono text-nota text-texto-suave"
        >
          {contador}
          {job.progress.failed > 0
            ? ` · ${job.progress.failed} com falha`
            : ''}
        </p>
      </div>

      {mostrarBarra ? (
        <BarraDeProgresso
          concluidas={job.progress.completed}
          total={total}
          rotulo={contador}
          emAndamento={emAndamento}
        />
      ) : null}

      <TiraDeVariacoes variacoes={job.variations} statusDoJob={job.status} />
    </div>
  );
}
