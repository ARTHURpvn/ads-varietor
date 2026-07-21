import type { ReactElement } from 'react';
import type { Variation } from '../api/types.ts';
import { useDownloadDeVariacao } from '../hooks/useDownloads.ts';
import { mensagemDeErro } from '../lib/erro.ts';
import { CartaoDeVariacao } from './CartaoDeVariacao.tsx';

interface PainelDeVariacoesProps {
  jobId: string;
  variacoes: Variation[];
  /** Texto mostrado quando ainda não há variação alguma. */
  mensagemVazia: string;
}

/**
 * Lista de variações com o download individual. Fonte única da lógica
 * de download por variação — usada na tela de progresso e na de resultados.
 */
export function PainelDeVariacoes({
  jobId,
  variacoes,
  mensagemVazia,
}: PainelDeVariacoesProps): ReactElement {
  const download = useDownloadDeVariacao();
  const variacaoEmDownload = download.isPending
    ? (download.variables?.variationId ?? null)
    : null;
  const variacaoComErro = download.isError
    ? (download.variables?.variationId ?? null)
    : null;
  const textoDoErro = download.isError ? mensagemDeErro(download.error) : null;

  if (variacoes.length === 0) {
    return (
      <p
        className="rounded-xl border border-dashed border-borda p-6
                   text-center text-sm text-texto-suave"
      >
        {mensagemVazia}
      </p>
    );
  }

  return (
    <ul className="grid gap-3 sm:grid-cols-2">
      {variacoes.map((variacao, indice) => (
        <CartaoDeVariacao
          key={variacao.variation_id}
          variacao={variacao}
          indice={indice}
          baixando={variacaoEmDownload === variacao.variation_id}
          erroDoDownload={
            variacaoComErro === variacao.variation_id ? textoDoErro : null
          }
          aoBaixar={() =>
            download.mutate({
              jobId,
              variationId: variacao.variation_id,
              indice,
            })
          }
        />
      ))}
    </ul>
  );
}
