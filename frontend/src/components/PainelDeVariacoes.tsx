import { useState, type ReactElement } from 'react';
import type { JobStatus, ProcessingMode, Variation } from '../api/types.ts';
import { useDownloadDeVariacao } from '../hooks/useDownloads.ts';
import { mensagemDeErro } from '../lib/erro.ts';
import {
  contarPorGrupo,
  pertenceAoGrupo,
  rotuloDoGrupo,
  type GrupoDeVariacoes,
} from '../lib/filtros.ts';
import { CartaoDeVariacao } from './CartaoDeVariacao.tsx';
import { Icone } from './Icone.tsx';

/** A partir daqui a lista deixa de ser varrível sem filtro. */
const MINIMO_PARA_FILTRAR = 6;

const GRUPOS: readonly GrupoDeVariacoes[] = [
  'todas',
  'prontas',
  'pendentes',
  'falhas',
];

interface PainelDeVariacoesProps {
  jobId: string;
  statusDoJob: JobStatus;
  modo: ProcessingMode;
  variacoes: Variation[];
  /** Texto mostrado quando ainda não há variação alguma. */
  mensagemVazia: string;
}

/**
 * Grade de saídas com download individual. Fonte única da lógica de
 * download por saída — usada na tela de progresso e na de resultados.
 */
export function PainelDeVariacoes({
  jobId,
  statusDoJob,
  modo,
  variacoes,
  mensagemVazia,
}: PainelDeVariacoesProps): ReactElement {
  const [grupo, setGrupo] = useState<GrupoDeVariacoes>('todas');

  if (variacoes.length === 0) {
    return <PainelVazio mensagem={mensagemVazia} />;
  }

  const contagem = contarPorGrupo(variacoes, statusDoJob);

  // Filtro só existe quando há mesmo o que separar. Se todas as saídas
  // estão na mesma situação — o caso dominante — sobrariam "Todas" e um
  // segundo chip devolvendo exatamente a mesma lista.
  const gruposComSaidas = GRUPOS.filter(
    (opcao) => opcao !== 'todas' && contagem[opcao] > 0,
  );
  const mostrarFiltro =
    variacoes.length >= MINIMO_PARA_FILTRAR && gruposComSaidas.length > 1;

  // A lista é repolida durante o processamento: o grupo escolhido pode
  // sumir debaixo do usuário (as pendentes viram prontas, o filtro some).
  // Sem isto ele ficaria preso numa lista vazia, sem chip para voltar.
  const grupoAtivo: GrupoDeVariacoes =
    mostrarFiltro && (grupo === 'todas' || contagem[grupo] > 0)
      ? grupo
      : 'todas';

  // O índice original vira o número do cartão e o do arquivo baixado,
  // então ele precisa sobreviver ao filtro.
  const visiveis = variacoes
    .map((variacao, indice) => ({ variacao, indice }))
    .filter((item) => pertenceAoGrupo(item.variacao, statusDoJob, grupoAtivo));

  return (
    <div className="flex flex-col gap-3">
      {mostrarFiltro ? (
        <div
          role="group"
          aria-label="Filtrar saídas por situação"
          className="flex flex-wrap items-center gap-1.5"
        >
          {(['todas', ...gruposComSaidas] as const).map((opcao) => (
            <BotaoDeGrupo
              key={opcao}
              grupo={opcao}
              quantidade={contagem[opcao]}
              ativo={grupoAtivo === opcao}
              aoSelecionar={() => setGrupo(opcao)}
            />
          ))}
        </div>
      ) : null}

      {visiveis.length === 0 ? (
        <PainelVazio
          mensagem={`Nenhuma saída nesta situação agora. Volte para
                     "Todas" para ver a lista inteira.`}
        />
      ) : (
        <ul
          className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3
                     2xl:grid-cols-4"
        >
          {visiveis.map((item) => (
            <ItemDeVariacao
              key={item.variacao.variation_id}
              jobId={jobId}
              statusDoJob={statusDoJob}
              modo={modo}
              variacao={item.variacao}
              indice={item.indice}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

interface BotaoDeGrupoProps {
  grupo: GrupoDeVariacoes;
  quantidade: number;
  ativo: boolean;
  aoSelecionar: () => void;
}

function BotaoDeGrupo({
  grupo,
  quantidade,
  ativo,
  aoSelecionar,
}: BotaoDeGrupoProps): ReactElement {
  return (
    <button
      type="button"
      aria-pressed={ativo}
      aria-label={`${rotuloDoGrupo(grupo)}: ${quantidade}`}
      onClick={aoSelecionar}
      className={`inline-flex min-h-8 items-center gap-1.5 rounded-lg border
                  px-2.5 py-1 text-micro font-semibold transition-colors
                  ${
                    ativo
                      ? 'border-destaque bg-destaque-suave text-destaque'
                      : 'border-borda bg-superficie text-texto-suave ' +
                        'hover:border-borda-forte hover:text-texto'
                  }`}
    >
      {rotuloDoGrupo(grupo)}
      <span className="font-mono text-selo text-texto-fraco">
        {quantidade}
      </span>
    </button>
  );
}

interface PainelVazioProps {
  mensagem: string;
}

function PainelVazio({ mensagem }: PainelVazioProps): ReactElement {
  return (
    <div
      className="flex flex-col items-center gap-2 rounded-xl border
                 border-dashed border-borda bg-superficie/50 px-6 py-10
                 text-center"
    >
      <span className="text-texto-fraco">
        <Icone nome="camadas" tamanho={22} />
      </span>

      <p className="max-w-sm text-nota text-texto-suave">{mensagem}</p>
    </div>
  );
}

interface ItemDeVariacaoProps {
  jobId: string;
  statusDoJob: JobStatus;
  modo: ProcessingMode;
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
  modo,
  variacao,
  indice,
}: ItemDeVariacaoProps): ReactElement {
  const download = useDownloadDeVariacao();

  return (
    <CartaoDeVariacao
      variacao={variacao}
      statusDoJob={statusDoJob}
      modo={modo}
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
