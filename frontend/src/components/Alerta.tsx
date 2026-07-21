import type { ReactElement } from 'react';
import { Botao } from './Botao.tsx';

export type TomDoAlerta = 'erro' | 'aviso' | 'informacao';

interface AlertaProps {
  tom?: TomDoAlerta;
  titulo: string;
  mensagem: string;
  rotuloDaAcao?: string;
  aoAcionar?: () => void;
  acaoCarregando?: boolean;
}

const ESTILO_POR_TOM: Record<TomDoAlerta, string> = {
  erro: 'border-erro/50 bg-erro/10',
  aviso: 'border-alerta/50 bg-alerta/10',
  informacao: 'border-borda bg-superficie-suave',
};

const ICONE_POR_TOM: Record<TomDoAlerta, string> = {
  erro: '!',
  aviso: '!',
  informacao: 'i',
};

export function Alerta({
  tom = 'erro',
  titulo,
  mensagem,
  rotuloDaAcao,
  aoAcionar,
  acaoCarregando = false,
}: AlertaProps): ReactElement {
  return (
    <div
      role={tom === 'erro' ? 'alert' : 'status'}
      className={`flex flex-col gap-3 rounded-xl border p-4 sm:flex-row
                  sm:items-center sm:justify-between ${ESTILO_POR_TOM[tom]}`}
    >
      <div className="flex items-start gap-3">
        <span
          aria-hidden="true"
          className="mt-0.5 flex size-6 shrink-0 items-center justify-center
                     rounded-full border border-current text-xs font-bold"
        >
          {ICONE_POR_TOM[tom]}
        </span>

        <div className="min-w-0">
          <p className="font-semibold text-texto">{titulo}</p>
          <p className="mt-1 text-sm text-texto-suave break-words">
            {mensagem}
          </p>
        </div>
      </div>

      {rotuloDaAcao !== undefined && aoAcionar !== undefined ? (
        <Botao
          variante="secundario"
          onClick={aoAcionar}
          carregando={acaoCarregando}
          className="shrink-0 self-start sm:self-auto"
        >
          {rotuloDaAcao}
        </Botao>
      ) : null}
    </div>
  );
}
