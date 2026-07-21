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

/** Seletor dos elementos que podem receber foco dentro do diálogo. */
const SELETOR_FOCAVEL = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

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
  const dialogoRef = useRef<HTMLDivElement>(null);
  const botaoCancelarRef = useRef<HTMLButtonElement>(null);

  // Foca o diálogo ao abrir e devolve o foco a quem o abriu ao fechar.
  useEffect(() => {
    const elementoAnterior =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;

    botaoCancelarRef.current?.focus();

    return () => {
      elementoAnterior?.focus();
    };
  }, []);

  // Escape fecha; Tab e Shift+Tab circulam dentro do diálogo.
  useEffect(() => {
    function aoPressionarTecla(evento: KeyboardEvent): void {
      if (evento.key === 'Escape') {
        aoCancelar();
        return;
      }

      if (evento.key !== 'Tab') {
        return;
      }

      const dialogo = dialogoRef.current;

      if (dialogo === null) {
        return;
      }

      const focaveis = Array.from(
        dialogo.querySelectorAll<HTMLElement>(SELETOR_FOCAVEL),
      );

      if (focaveis.length === 0) {
        evento.preventDefault();
        dialogo.focus();
        return;
      }

      const primeiro = focaveis[0];
      const ultimo = focaveis[focaveis.length - 1];

      if (primeiro === undefined || ultimo === undefined) {
        return;
      }

      const ativo = document.activeElement;
      const focoEstaFora = !dialogo.contains(ativo);

      if (evento.shiftKey && (ativo === primeiro || focoEstaFora)) {
        evento.preventDefault();
        ultimo.focus();
        return;
      }

      if (!evento.shiftKey && (ativo === ultimo || focoEstaFora)) {
        evento.preventDefault();
        primeiro.focus();
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
        ref={dialogoRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={tituloId}
        aria-describedby={descricaoId}
        tabIndex={-1}
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
