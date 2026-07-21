import type { ReactElement } from 'react';

interface BarraDeProgressoProps {
  concluidas: number;
  total: number;
  /** Descrição textual associada, lida por leitores de tela. */
  rotulo: string;
  /** true enquanto o trabalho ainda avança: liga a listra em movimento. */
  emAndamento?: boolean;
}

export function BarraDeProgresso({
  concluidas,
  total,
  rotulo,
  emAndamento = false,
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
      className="h-2 w-full overflow-hidden rounded-full bg-fundo-alto
                 ring-1 ring-borda ring-inset"
    >
      <div
        className={`h-full rounded-full bg-destaque transition-[width]
                    duration-500 ease-out
                    ${emAndamento ? 'listra-ativa' : ''}`}
        style={{ width: `${percentual}%` }}
      />
    </div>
  );
}
