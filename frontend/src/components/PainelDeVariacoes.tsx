import type { ReactElement } from 'react';
import type { JobStatus, Variation } from '../api/types.ts';
import { useDownloadDeVariacao } from '../hooks/useDownloads.ts';
import { mensagemDeErro } from '../lib/erro.ts';
import { CartaoDeVariacao } from './CartaoDeVariacao.tsx';

interface PainelDeVariacoesProps {
  jobId: string;
  statusDoJob: JobStatus;
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
  statusDoJob,
  variacoes,
  mensagemVazia,
}: PainelDeVariacoesProps): ReactElement {
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
        <ItemDeVariacao
          key={variacao.variation_id}
          jobId={jobId}
          statusDoJob={statusDoJob}
          variacao={variacao}
          indice={indice}
        />
      ))}
    </ul>
  );
}

interface ItemDeVariacaoProps {
  jobId: string;
  statusDoJob: JobStatus;
  variacao: Variation;
  indice: number;
}

/**
 * Cada variação tem sua própria mutação de download. Compartilhar uma
 * só entre todos os cartões faria dois downloads simultâneos disputarem
 * o mesmo spinner e a mesma mensagem de erro.
 */
function ItemDeVariacao({
  jobId,
  statusDoJob,
  variacao,
  indice,
}: ItemDeVariacaoProps): ReactElement {
  const download = useDownloadDeVariacao();

  return (
    <CartaoDeVariacao
      variacao={variacao}
      statusDoJob={statusDoJob}
      indice={indice}
      baixando={download.isPending}
      erroDoDownload={
        download.isError ? mensagemDeErro(download.error) : null
      }
      aoBaixar={() =>
        download.mutate({
          jobId,
          variationId: variacao.variation_id,
          indice,
        })
      }
    />
  );
}
