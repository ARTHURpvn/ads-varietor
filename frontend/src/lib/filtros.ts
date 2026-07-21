/**
 * Agrupamento das saídas na tela de resultados.
 *
 * Com 50 saídas na tela, "achar as que falharam" vira uma varredura manual.
 * Os grupos abaixo existem só para reduzir a lista ao que o usuário quer
 * olhar agora — não trocam nem escondem nenhum dado da API.
 */

import type { JobStatus, Variation } from '../api/types.ts';
import { statusExibidoDaVariacao } from './mensagens.ts';

export type GrupoDeVariacoes = 'todas' | 'prontas' | 'pendentes' | 'falhas';

export interface ContagemPorGrupo {
  todas: number;
  prontas: number;
  pendentes: number;
  falhas: number;
}

export function pertenceAoGrupo(
  variacao: Variation,
  statusDoJob: JobStatus,
  grupo: GrupoDeVariacoes,
): boolean {
  if (grupo === 'todas') {
    return true;
  }

  const status = statusExibidoDaVariacao(variacao, statusDoJob);

  switch (grupo) {
    case 'prontas':
      return status === 'completed';
    case 'pendentes':
      return status === 'pending' || status === 'running';
    case 'falhas':
      return status === 'failed' || status === 'interrompida';
  }
}

export function contarPorGrupo(
  variacoes: readonly Variation[],
  statusDoJob: JobStatus,
): ContagemPorGrupo {
  const contagem: ContagemPorGrupo = {
    todas: variacoes.length,
    prontas: 0,
    pendentes: 0,
    falhas: 0,
  };

  for (const variacao of variacoes) {
    if (pertenceAoGrupo(variacao, statusDoJob, 'prontas')) {
      contagem.prontas += 1;
    } else if (pertenceAoGrupo(variacao, statusDoJob, 'pendentes')) {
      contagem.pendentes += 1;
    } else {
      contagem.falhas += 1;
    }
  }

  return contagem;
}

/** Rótulo do grupo, já com a contagem entre parênteses. */
export function rotuloDoGrupo(grupo: GrupoDeVariacoes): string {
  switch (grupo) {
    case 'todas':
      return 'Todas';
    case 'prontas':
      return 'Prontas';
    case 'pendentes':
      return 'Na fila';
    case 'falhas':
      return 'Com falha';
  }
}
