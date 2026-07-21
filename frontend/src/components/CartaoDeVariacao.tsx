import type { ReactElement } from 'react';
import type { JobStatus, ProcessingMode, Variation } from '../api/types.ts';
import { corDoHash } from '../lib/corDoHash.ts';
import { normalizarHash } from '../lib/hash.ts';
import {
  motivoDaFalha,
  motivoDaInterrupcao,
  resumoDaVariacao,
  statusExibidoDaVariacao,
  type StatusExibidoDaVariacao,
} from '../lib/mensagens.ts';
import { tituloDaSaida } from '../lib/modos.ts';
import { formatarTamanho } from '../lib/videoFile.ts';
import { Botao } from './Botao.tsx';
import { Icone } from './Icone.tsx';
import { IdentificacaoDoArquivo } from './IdentificacaoDoArquivo.tsx';
import { SeloDeStatus } from './SeloDeStatus.tsx';

interface CartaoDeVariacaoProps {
  variacao: Variation;
  /** Status do trabalho: define se uma variação na fila ainda avança. */
  statusDoJob: JobStatus;
  /** Modo do trabalho: em `metadata_only` não há parâmetros aplicados. */
  modo: ProcessingMode;
  indice: number;
  baixando: boolean;
  erroDoDownload: string | null;
  aoBaixar: () => void;
}

/** Cor da faixa lateral quando a saída ainda não tem identificação. */
const FAIXA_SEM_HASH: Record<StatusExibidoDaVariacao, string> = {
  pending: 'var(--c-borda-forte)',
  running: 'var(--c-destaque)',
  completed: 'var(--c-borda-forte)',
  failed: 'var(--c-erro)',
  interrompida: 'var(--c-alerta)',
};

export function CartaoDeVariacao({
  variacao,
  statusDoJob,
  modo,
  indice,
  baixando,
  erroDoDownload,
  aoBaixar,
}: CartaoDeVariacaoProps): ReactElement {
  const numero = String(indice + 1).padStart(2, '0');
  const statusExibido = statusExibidoDaVariacao(variacao, statusDoJob);
  const hash = normalizarHash(variacao.md5);
  const concluida = statusExibido === 'completed';
  const falhou = statusExibido === 'failed';
  const interrompida = statusExibido === 'interrompida';

  // A faixa lateral é a cor da própria identificação do arquivo. Numa
  // grade de 50 saídas ela é o que permite achar uma delas de relance —
  // e duplicatas aparecem como duas faixas de cor idêntica.
  const corDaFaixa =
    concluida && hash !== null
      ? corDoHash(hash)
      : FAIXA_SEM_HASH[statusExibido];

  // Quem foi pego pelo cancelamento já chega aqui como `interrompida`
  // (ver `statusExibidoDaVariacao`), com selo neutro e texto de
  // interrupção. `failed` daqui em diante é falha de verdade.
  const resumo = resumoDaVariacao(variacao, modo);

  return (
    <li
      className="relative flex flex-col gap-2 overflow-hidden rounded-lg
                 border border-borda bg-superficie py-2.5 pr-3 pl-4
                 shadow-[var(--sombra-cartao)] transition-colors
                 hover:border-borda-forte"
    >
      <span
        aria-hidden="true"
        className="absolute inset-y-0 left-0 w-1"
        style={{ backgroundColor: corDaFaixa }}
      />

      <div className="flex items-center gap-2">
        <h3 className="font-mono text-micro font-semibold text-texto-suave">
          <span className="sr-only">{tituloDaSaida(modo)} </span>
          {numero}
        </h3>

        <SeloDeStatus status={statusExibido} />

        {concluida && variacao.size_bytes !== null ? (
          <span className="ml-auto font-mono text-micro text-texto-fraco">
            {formatarTamanho(variacao.size_bytes)}
          </span>
        ) : null}
      </div>

      {concluida && hash !== null ? (
        <IdentificacaoDoArquivo
          rotulo={`Identificação da ${tituloDaSaida(modo)} ${numero}`}
          hash={hash}
          compacto
        />
      ) : null}

      {concluida ? (
        <p
          title={resumo}
          className="line-clamp-2 font-mono text-micro break-words
                     text-texto-fraco"
        >
          {resumo}
        </p>
      ) : null}

      {falhou ? (
        <p className="text-micro text-erro">{motivoDaFalha(variacao)}</p>
      ) : null}

      {interrompida ? (
        <p className="text-micro text-alerta">
          {motivoDaInterrupcao(statusDoJob)}
        </p>
      ) : null}

      {concluida ? (
        <div className="flex flex-col gap-1.5">
          <Botao
            variante="secundario"
            tamanho="compacto"
            carregando={baixando}
            onClick={aoBaixar}
            icone={<Icone nome="baixar" tamanho={14} />}
            aria-label={`Baixar ${tituloDaSaida(modo)} ${numero}`}
            className="w-full"
          >
            Baixar
          </Botao>

          {erroDoDownload !== null ? (
            <p role="alert" className="text-micro text-erro">
              {erroDoDownload}
            </p>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}
