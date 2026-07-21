import type { ReactElement } from 'react';
import type { JobStatus, Variation } from '../api/types.ts';
import {
  motivoDaFalha,
  motivoDaInterrupcao,
  resumoDosParametros,
  rotuloDoStatusDaVariacao,
  statusExibidoDaVariacao,
  type StatusExibidoDaVariacao,
} from '../lib/mensagens.ts';
import { formatarTamanho } from '../lib/videoFile.ts';
import { Botao } from './Botao.tsx';

interface CartaoDeVariacaoProps {
  variacao: Variation;
  /** Status do trabalho: define se uma variação na fila ainda avança. */
  statusDoJob: JobStatus;
  indice: number;
  baixando: boolean;
  erroDoDownload: string | null;
  aoBaixar: () => void;
}

const ESTILO_DA_ETIQUETA: Record<StatusExibidoDaVariacao, string> = {
  pending: 'border-borda text-texto-suave',
  running: 'border-destaque text-destaque',
  completed: 'border-sucesso text-sucesso',
  failed: 'border-erro text-erro',
  interrompida: 'border-alerta text-alerta',
};

export function CartaoDeVariacao({
  variacao,
  statusDoJob,
  indice,
  baixando,
  erroDoDownload,
  aoBaixar,
}: CartaoDeVariacaoProps): ReactElement {
  const numero = String(indice + 1).padStart(2, '0');
  const statusExibido = statusExibidoDaVariacao(variacao, statusDoJob);
  const concluida = statusExibido === 'completed';
  const falhou = statusExibido === 'failed';
  const interrompida = statusExibido === 'interrompida';

  // O backend marca como `failed` as variações que o cancelamento pegou
  // pelo meio. Sem detalhe do erro, o texto honesto é o de interrupção.
  const semDetalheDoErro = (variacao.error ?? '').trim().length === 0;
  const mensagemDaFalha =
    statusDoJob === 'cancelled' && semDetalheDoErro
      ? motivoDaInterrupcao(statusDoJob)
      : motivoDaFalha(variacao);

  return (
    <li
      className="flex flex-col gap-3 rounded-xl border border-borda
                 bg-superficie p-4"
    >
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-base font-semibold text-texto">
          Variação {numero}
        </h3>

        <span
          className={`rounded-full border px-2 py-0.5 text-xs font-semibold
                      ${ESTILO_DA_ETIQUETA[statusExibido]}`}
        >
          {rotuloDoStatusDaVariacao(statusExibido)}
        </span>

        {concluida && variacao.size_bytes !== null ? (
          <span className="text-xs text-texto-suave">
            {formatarTamanho(variacao.size_bytes)}
          </span>
        ) : null}
      </div>

      <p className="text-xs text-texto-suave break-words">
        {resumoDosParametros(variacao)}
      </p>

      {falhou ? (
        <p className="rounded-lg bg-erro/10 px-3 py-2 text-sm text-erro">
          {mensagemDaFalha}
        </p>
      ) : null}

      {interrompida ? (
        <p className="rounded-lg bg-alerta/10 px-3 py-2 text-sm text-alerta">
          {motivoDaInterrupcao(statusDoJob)}
        </p>
      ) : null}

      {concluida ? (
        <div className="flex flex-col gap-2">
          <Botao
            variante="secundario"
            carregando={baixando}
            onClick={aoBaixar}
            className="self-start"
          >
            Baixar vídeo
          </Botao>

          {erroDoDownload !== null ? (
            <p role="alert" className="text-sm text-erro">
              {erroDoDownload}
            </p>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}
