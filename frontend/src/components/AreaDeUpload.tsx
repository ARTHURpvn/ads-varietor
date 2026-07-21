import { useId, useState, type DragEvent, type ReactElement } from 'react';
import {
  ACCEPT_ATTRIBUTE,
  formatarTamanho,
  validarArquivoDeVideo,
} from '../lib/videoFile.ts';
import { Icone } from './Icone.tsx';

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
    ? 'border-destaque bg-destaque-suave'
    : 'border-borda-forte bg-superficie hover:border-destaque ' +
      'hover:bg-destaque-suave/40';

  return (
    <div>
      <label
        htmlFor={inputId}
        onDrop={aoSoltar}
        onDragOver={aoArrastarSobre}
        onDragEnter={aoArrastarSobre}
        onDragLeave={() => setArrastando(false)}
        className={`group flex w-full cursor-pointer flex-col items-center
                    gap-3 rounded-xl border border-dashed px-4 py-9
                    text-center transition-colors
                    has-[input:focus-visible]:border-destaque
                    has-[input:focus-visible]:outline
                    has-[input:focus-visible]:outline-2
                    has-[input:focus-visible]:outline-destaque
                    has-[input:focus-visible]:outline-offset-2
                    ${estiloDaBorda}
                    ${desabilitado ? 'cursor-not-allowed opacity-60' : ''}`}
      >
        <span
          className={`flex size-11 items-center justify-center rounded-xl
                      border transition-colors
                      ${
                        arrastando
                          ? 'border-destaque bg-destaque text-sobre-destaque'
                          : 'border-borda bg-superficie-suave text-texto-suave'
                      }`}
        >
          <Icone nome="video" tamanho={22} />
        </span>

        <span className="flex flex-col gap-1">
          <span className="text-guia font-semibold text-texto">
            {arrastando ? 'Solte para carregar' : 'Arraste seu vídeo aqui'}
          </span>

          <span id={dicaId} className="text-nota text-texto-suave">
            ou clique para escolher um arquivo MP4, MOV ou WebM
          </span>
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
          className="mt-2 flex flex-wrap items-center gap-x-2.5 gap-y-1
                     rounded-lg border border-borda bg-superficie px-3 py-2
                     text-nota animate-surgir"
          aria-live="polite"
        >
          <span className="text-destaque">
            <Icone nome="arquivo" tamanho={15} />
          </span>

          <span className="min-w-0 break-all font-medium text-texto">
            {arquivoSelecionado.name}
          </span>

          <span className="ml-auto font-mono text-micro text-texto-suave">
            {formatarTamanho(arquivoSelecionado.size)}
          </span>
        </p>
      ) : null}
    </div>
  );
}
