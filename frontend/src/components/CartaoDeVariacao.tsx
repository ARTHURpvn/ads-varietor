import type { ReactElement } from 'react';
import type { Variation, VariationStatus } from '../api/types.ts';
import {
  motivoDaFalha,
  resumoDosParametros,
  rotuloDoStatusDaVariacao,
} from '../lib/mensagens.ts';
import { formatarTamanho } from '../lib/videoFile.ts';
import { Botao } from './Botao.tsx';

interface CartaoDeVariacaoProps {
  variacao: Variation;
  indice: number;
  baixando: boolean;
  erroDoDownload: string | null;
  aoBaixar: () => void;
}

const ESTILO_DA_ETIQUETA: Record<VariationStatus, string> = {
  pending: 'border-borda text-texto-suave',
  running: 'border-destaque text-destaque',
  completed: 'border-sucesso text-sucesso',
  failed: 'border-erro text-erro',
};

export function CartaoDeVariacao({
  variacao,
  indice,
  baixando,
  erroDoDownload,
  aoBaixar,
}: CartaoDeVariacaoProps): ReactElement {
  const numero = String(indice + 1).padStart(2, '0');
  const concluida = variacao.status === 'completed';
  const falhou = variacao.status === 'failed';

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
                      ${ESTILO_DA_ETIQUETA[variacao.status]}`}
        >
          {rotuloDoStatusDaVariacao(variacao.status)}
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
          {motivoDaFalha(variacao)}
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
