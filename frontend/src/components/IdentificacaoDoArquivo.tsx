import { useEffect, useState, type ReactElement } from 'react';
import { corDoHash } from '../lib/corDoHash.ts';
import { encurtarHash } from '../lib/hash.ts';
import { Icone } from './Icone.tsx';

type EstadoDaCopia = 'inativo' | 'copiado' | 'falhou';

const SEGUNDOS_DE_AVISO = 3_000;

interface IdentificacaoDoArquivoProps {
  /** O que este hash identifica, ex.: "Arquivo original". */
  rotulo: string;
  hash: string;
  /**
   * Variante de uma linha só, para caber dentro do cartão de saída
   * numa grade com dezenas deles.
   */
  compacto?: boolean;
}

/**
 * Mostra um MD5 em fonte monoespaçada, encurtado para caber em telas
 * estreitas, com a cor derivada dele ao lado. O valor completo continua
 * acessível pelo `title`, pelo texto lido por leitor de tela e pelo botão
 * de copiar.
 */
export function IdentificacaoDoArquivo({
  rotulo,
  hash,
  compacto = false,
}: IdentificacaoDoArquivoProps): ReactElement {
  const [estado, setEstado] = useState<EstadoDaCopia>('inativo');

  useEffect(() => {
    if (estado === 'inativo') {
      return;
    }

    const temporizador = window.setTimeout(
      () => setEstado('inativo'),
      SEGUNDOS_DE_AVISO,
    );

    return () => window.clearTimeout(temporizador);
  }, [estado]);

  async function copiar(): Promise<void> {
    try {
      await navigator.clipboard.writeText(hash);
      setEstado('copiado');
    } catch {
      // Sem permissão ou fora de contexto seguro: revelamos o valor
      // inteiro para o usuário copiar na mão.
      setEstado('falhou');
    }
  }

  return (
    <div className="flex min-w-0 flex-col gap-1">
      <div className="flex min-w-0 items-center gap-2">
        {compacto ? null : (
          <span className="text-micro text-texto-suave">{rotulo}</span>
        )}

        <code
          title={hash}
          className="flex min-w-0 items-center gap-2 rounded-md border
                     border-borda bg-fundo-alto px-2 py-1 font-mono
                     text-micro text-texto"
        >
          <span
            aria-hidden="true"
            className="size-2.5 shrink-0 rounded-[3px]"
            style={{ backgroundColor: corDoHash(hash) }}
          />
          <span aria-hidden="true" className="truncate">
            {encurtarHash(hash, compacto ? 6 : 8)}
          </span>
          <span className="sr-only">{`${rotulo}: ${hash}`}</span>
        </code>

        <button
          type="button"
          onClick={() => void copiar()}
          aria-label={`Copiar identificação: ${rotulo}`}
          className="inline-flex size-7 shrink-0 items-center justify-center
                     rounded-md border border-transparent text-texto-fraco
                     transition-colors hover:border-borda
                     hover:bg-superficie-suave hover:text-texto"
        >
          {estado === 'copiado' ? (
            <span className="text-sucesso">
              <Icone nome="confirmado" tamanho={14} />
            </span>
          ) : (
            <Icone nome="copiar" tamanho={14} />
          )}
        </button>
      </div>

      {estado === 'copiado' ? (
        <p role="status" className="text-micro text-sucesso">
          Identificação copiada.
        </p>
      ) : null}

      {estado === 'falhou' ? (
        <p role="alert" className="text-micro text-erro">
          Não deu para copiar automaticamente. Selecione o código abaixo:{' '}
          <span className="font-mono break-all text-texto">{hash}</span>
        </p>
      ) : null}
    </div>
  );
}
