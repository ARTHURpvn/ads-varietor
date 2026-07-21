import { useEffect, useId, useRef, type ReactElement } from 'react';
import { Botao } from './Botao.tsx';

interface DialogoDeConfirmacaoProps {
  titulo: string;
  descricao: string;
  rotuloConfirmar: string;
  rotuloCancelar: string;
  confirmando?: boolean;
  aoConfirmar: () => void;
  aoCancelar: () => void;
}

export function DialogoDeConfirmacao({
  titulo,
  descricao,
  rotuloConfirmar,
  rotuloCancelar,
  confirmando = false,
  aoConfirmar,
  aoCancelar,
}: DialogoDeConfirmacaoProps): ReactElement {
  const tituloId = useId();
  const descricaoId = useId();
  const botaoCancelarRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    botaoCancelarRef.current?.focus();
  }, []);

  useEffect(() => {
    function aoPressionarTecla(evento: KeyboardEvent): void {
      if (evento.key === 'Escape') {
        aoCancelar();
      }
    }

    document.addEventListener('keydown', aoPressionarTecla);
    return () => document.removeEventListener('keydown', aoPressionarTecla);
  }, [aoCancelar]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/70
                 p-4 sm:items-center"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={tituloId}
        aria-describedby={descricaoId}
        className="w-full max-w-md rounded-2xl border border-borda
                   bg-superficie p-6 shadow-2xl"
      >
        <h2 id={tituloId} className="text-lg font-semibold text-texto">
          {titulo}
        </h2>

        <p id={descricaoId} className="mt-2 text-sm text-texto-suave">
          {descricao}
        </p>

        <div className="mt-6 flex flex-col gap-2 sm:flex-row sm:justify-end">
          <Botao
            ref={botaoCancelarRef}
            variante="secundario"
            onClick={aoCancelar}
          >
            {rotuloCancelar}
          </Botao>

          <Botao
            variante="perigo"
            onClick={aoConfirmar}
            carregando={confirmando}
          >
            {rotuloConfirmar}
          </Botao>
        </div>
      </div>
    </div>
  );
}
