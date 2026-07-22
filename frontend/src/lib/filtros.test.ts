import { describe, expect, it } from 'vitest';

import type { Variation, VariationStatus } from '../api/types.ts';
import {
  contarPorGrupo,
  pertenceAoGrupo,
  rotuloDoGrupo,
} from './filtros.ts';

function variacao(id: string, status: VariationStatus): Variation {
  return {
    variation_id: id,
    status,
    error: null,
    size_bytes: status === 'completed' ? 1024 : null,
    md5: status === 'completed' ? `${id}0123456789abcdef` : null,
    progress: status === 'completed' ? 100 : 0,
    params: {
      speed: 1,
      filter_type: 'eq',
      filter_value: 0.1,
      background_color: '#000000',
      video_scale: 1,
      noise_audio: false,
    },
  };
}

describe('pertenceAoGrupo', () => {
  it('aceita qualquer variação no grupo "todas"', () => {
    expect(pertenceAoGrupo(variacao('a', 'failed'), 'running', 'todas')).toBe(
      true,
    );
  });

  it('separa prontas, pendentes e falhas', () => {
    const pronta = variacao('a', 'completed');
    const naFila = variacao('b', 'pending');
    const comFalha = variacao('c', 'failed');

    expect(pertenceAoGrupo(pronta, 'running', 'prontas')).toBe(true);
    expect(pertenceAoGrupo(naFila, 'running', 'pendentes')).toBe(true);
    expect(pertenceAoGrupo(comFalha, 'running', 'falhas')).toBe(true);
    expect(pertenceAoGrupo(pronta, 'running', 'falhas')).toBe(false);
  });

  it('conta como falha a variação interrompida por cancelamento', () => {
    const naFila = variacao('b', 'pending');

    expect(pertenceAoGrupo(naFila, 'cancelled', 'pendentes')).toBe(false);
    expect(pertenceAoGrupo(naFila, 'cancelled', 'falhas')).toBe(true);
  });
});

describe('contarPorGrupo', () => {
  it('soma cada variação em exatamente um grupo', () => {
    const lista = [
      variacao('a', 'completed'),
      variacao('b', 'completed'),
      variacao('c', 'running'),
      variacao('d', 'failed'),
    ];

    const contagem = contarPorGrupo(lista, 'running');

    expect(contagem).toEqual({
      todas: 4,
      prontas: 2,
      pendentes: 1,
      falhas: 1,
    });
    expect(contagem.prontas + contagem.pendentes + contagem.falhas).toBe(
      contagem.todas,
    );
  });

  it('devolve tudo zerado quando não há variações', () => {
    expect(contarPorGrupo([], 'pending')).toEqual({
      todas: 0,
      prontas: 0,
      pendentes: 0,
      falhas: 0,
    });
  });
});

describe('rotuloDoGrupo', () => {
  it('devolve rótulo em português para cada grupo', () => {
    expect(rotuloDoGrupo('todas')).toBe('Todas');
    expect(rotuloDoGrupo('prontas')).toBe('Prontas');
    expect(rotuloDoGrupo('pendentes')).toBe('Na fila');
    expect(rotuloDoGrupo('falhas')).toBe('Com falha');
  });
});
