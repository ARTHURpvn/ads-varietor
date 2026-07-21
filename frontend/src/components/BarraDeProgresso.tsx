import type { ReactElement } from 'react';

interface BarraDeProgressoProps {
  concluidas: number;
  total: number;
  /** Descrição textual associada, lida por leitores de tela. */
  rotulo: string;
}

export function BarraDeProgresso({
  concluidas,
  total,
  rotulo,
}: BarraDeProgressoProps): ReactElement {
  const percentual =
    total > 0 ? Math.min(100, Math.round((concluidas / total) * 100)) : 0;

  return (
    <div
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={total}
      aria-valuenow={concluidas}
      aria-valuetext={rotulo}
      aria-label="Progresso da geração de variações"
      className="h-3 w-full overflow-hidden rounded-full bg-superficie-suave"
    >
      <div
        className="h-full rounded-full bg-destaque transition-all
                   duration-500 ease-out"
        style={{ width: `${percentual}%` }}
      />
    </div>
  );
}
