import type { ReactElement } from 'react';
import type { JobStatus, Variation } from '../api/types.ts';
import { corDoHash } from '../lib/corDoHash.ts';
import { normalizarHash } from '../lib/hash.ts';
import {
  rotuloDoStatusDaVariacao,
  statusExibidoDaVariacao,
  type StatusExibidoDaVariacao,
} from '../lib/mensagens.ts';

interface TiraDeVariacoesProps {
  variacoes: readonly Variation[];
  statusDoJob: JobStatus;
}

/** Cor da célula enquanto a saída ainda não tem identificação própria. */
const COR_SEM_HASH: Record<StatusExibidoDaVariacao, string> = {
  pending: 'var(--c-borda)',
  running: 'var(--c-destaque)',
  completed: 'var(--c-borda-forte)',
  failed: 'var(--c-erro)',
  interrompida: 'var(--c-alerta)',
};

/**
 * Uma célula por saída, na ordem em que foram pedidas. Enquanto o trabalho
 * corre, a tira vai se preenchendo com a cor de cada identificação — dá o
 * andamento de relance, sem obrigar a contar cartões.
 *
 * É redundante de propósito: o contador e a barra ao lado carregam a mesma
 * informação em texto, então a tira não precisa ser lida por leitor de tela.
 */
export function TiraDeVariacoes({
  variacoes,
  statusDoJob,
}: TiraDeVariacoesProps): ReactElement | null {
  if (variacoes.length === 0) {
    return null;
  }

  return (
    <ul aria-hidden="true" className="flex flex-wrap gap-1">
      {variacoes.map((variacao, indice) => {
        const status = statusExibidoDaVariacao(variacao, statusDoJob);
        const hash = normalizarHash(variacao.md5);
        const cor =
          status === 'completed' && hash !== null
            ? corDoHash(hash)
            : COR_SEM_HASH[status];

        return (
          <li
            key={variacao.variation_id}
            title={`${String(indice + 1).padStart(2, '0')} · ${rotuloDoStatusDaVariacao(status)}`}
            className={`h-2.5 w-4 rounded-[3px] transition-colors
                        duration-300
                        ${status === 'running' ? 'animate-pulsar' : ''}`}
            style={{ backgroundColor: cor }}
          />
        );
      })}
    </ul>
  );
}
