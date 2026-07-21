import type { ReactElement } from 'react';

interface TelaDeCarregamentoProps {
  mensagem: string;
}

export function TelaDeCarregamento({
  mensagem,
}: TelaDeCarregamentoProps): ReactElement {
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex flex-col items-center gap-4 rounded-2xl border
                 border-borda bg-superficie p-10 text-center"
    >
      <span
        aria-hidden="true"
        className="size-8 animate-spin rounded-full border-4 border-borda
                   border-t-destaque"
      />
      <p className="text-sm text-texto-suave">{mensagem}</p>
    </div>
  );
}
