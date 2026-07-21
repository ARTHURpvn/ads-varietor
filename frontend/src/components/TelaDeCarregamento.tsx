import type { ReactElement } from 'react';

interface TelaDeCarregamentoProps {
  mensagem: string;
}

/**
 * Espera curta antes de os dados chegarem. As três células imitam a tira
 * de saídas da tela de progresso, para a transição não parecer um corte.
 */
export function TelaDeCarregamento({
  mensagem,
}: TelaDeCarregamentoProps): ReactElement {
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex flex-col items-center gap-4 rounded-xl border
                 border-borda bg-superficie px-6 py-12 text-center
                 shadow-[var(--sombra-cartao)]"
    >
      <span aria-hidden="true" className="flex gap-1.5">
        {[0, 1, 2].map((posicao) => (
          <span
            key={posicao}
            className="h-2.5 w-6 animate-pulsar rounded-[3px] bg-destaque"
            style={{ animationDelay: `${posicao * 200}ms` }}
          />
        ))}
      </span>

      <p className="text-nota text-texto-suave">{mensagem}</p>
    </div>
  );
}
