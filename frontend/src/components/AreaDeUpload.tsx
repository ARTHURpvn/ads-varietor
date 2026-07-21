import { useId, useState, type DragEvent, type ReactElement } from 'react';
import {
  ACCEPT_ATTRIBUTE,
  formatarTamanho,
  validarArquivoDeVideo,
} from '../lib/videoFile.ts';

interface AreaDeUploadProps {
  arquivoSelecionado: File | null;
  desabilitado?: boolean;
  aoSelecionar: (arquivo: File) => void;
  aoRejeitar: (mensagem: string) => void;
}

/**
 * Seleção de vídeo por arrastar-e-soltar OU pelo input de arquivo,
 * que permanece acessível por teclado e leitores de tela.
 */
export function AreaDeUpload({
  arquivoSelecionado,
  desabilitado = false,
  aoSelecionar,
  aoRejeitar,
}: AreaDeUploadProps): ReactElement {
  const inputId = useId();
  const dicaId = useId();
  const [arrastando, setArrastando] = useState(false);

  function processarArquivo(arquivo: File | undefined): void {
    if (arquivo === undefined) {
      aoRejeitar('Não recebemos nenhum arquivo. Tente de novo.');
      return;
    }

    const resultado = validarArquivoDeVideo(arquivo);

    if (resultado.valido) {
      aoSelecionar(resultado.arquivo);
    } else {
      aoRejeitar(resultado.mensagem);
    }
  }

  function aoSoltar(evento: DragEvent<HTMLLabelElement>): void {
    evento.preventDefault();
    setArrastando(false);

    if (desabilitado) {
      return;
    }

    processarArquivo(evento.dataTransfer.files[0]);
  }

  function aoArrastarSobre(evento: DragEvent<HTMLLabelElement>): void {
    evento.preventDefault();

    if (!desabilitado) {
      setArrastando(true);
    }
  }

  const estiloDaBorda = arrastando
    ? 'border-destaque bg-destaque/10'
    : 'border-borda bg-superficie-suave/40 hover:border-destaque/70';

  return (
    <div>
      <label
        htmlFor={inputId}
        onDrop={aoSoltar}
        onDragOver={aoArrastarSobre}
        onDragEnter={aoArrastarSobre}
        onDragLeave={() => setArrastando(false)}
        className={`flex w-full cursor-pointer flex-col items-center gap-2
                    rounded-2xl border-2 border-dashed px-4 py-10 text-center
                    transition-colors
                    has-[input:focus-visible]:border-destaque
                    has-[input:focus-visible]:outline
                    has-[input:focus-visible]:outline-3
                    has-[input:focus-visible]:outline-destaque
                    has-[input:focus-visible]:outline-offset-2
                    ${estiloDaBorda}
                    ${desabilitado ? 'cursor-not-allowed opacity-60' : ''}`}
      >
        <span aria-hidden="true" className="text-3xl">
          🎬
        </span>

        <span className="text-base font-semibold text-texto">
          Arraste seu vídeo aqui
        </span>

        <span id={dicaId} className="text-sm text-texto-suave">
          ou clique para escolher um arquivo MP4, MOV ou WebM
        </span>

        <input
          id={inputId}
          type="file"
          accept={ACCEPT_ATTRIBUTE}
          disabled={desabilitado}
          aria-describedby={dicaId}
          className="sr-only"
          onChange={(evento) => {
            processarArquivo(evento.target.files?.[0]);
            // Permite reenviar o mesmo arquivo depois de um erro.
            evento.target.value = '';
          }}
        />
      </label>

      {arquivoSelecionado !== null ? (
        <p
          className="mt-3 flex flex-wrap items-center gap-2 rounded-lg
                     border border-borda bg-superficie px-3 py-2 text-sm"
          aria-live="polite"
        >
          <span aria-hidden="true">📄</span>
          <span className="min-w-0 break-all font-medium text-texto">
            {arquivoSelecionado.name}
          </span>
          <span className="text-texto-suave">
            {formatarTamanho(arquivoSelecionado.size)}
          </span>
        </p>
      ) : null}
    </div>
  );
}
