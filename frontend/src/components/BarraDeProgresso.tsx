import type { ReactElement } from 'react';

interface BarraDeProgressoProps {
  /** Andamento real de 0 a 100, já contando variações pela metade. */
  percentual: number;
  /** Descrição textual associada, lida por leitores de tela. */
  rotulo: string;
  /** true enquanto o trabalho ainda avança: liga a listra em movimento. */
  emAndamento?: boolean;
}

export function BarraDeProgresso({
  percentual,
  rotulo,
  emAndamento = false,
}: BarraDeProgressoProps): ReactElement {
  const largura = Math.min(100, Math.max(0, percentual));

  return (
    <div
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(largura)}
      aria-valuetext={rotulo}
      aria-label="Progresso da geração de variações"
      className="h-2 w-full overflow-hidden rounded-full bg-fundo-alto
                 ring-1 ring-borda ring-inset"
    >
      {/*
        A transição acompanha o intervalo de polling: o servidor manda um
        valor novo a cada 1 a 5 segundos, e sem a transição longa a barra
        daria saltos visíveis entre uma resposta e outra.
      */}
      <div
        className={`h-full rounded-full bg-destaque transition-[width]
                    duration-1000 ease-linear
                    ${emAndamento ? 'listra-ativa' : ''}`}
        style={{ width: `${largura}%` }}
      />
    </div>
  );
}
