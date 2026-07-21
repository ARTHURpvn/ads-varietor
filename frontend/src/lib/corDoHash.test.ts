import { describe, expect, it } from 'vitest';
import { corDoHash } from './corDoHash.ts';

describe('corDoHash', () => {
  it('devolve a mesma cor para o mesmo hash', () => {
    const hash = '9f2ab1c4d5e6f708192a3b4c5d6e7f80';

    expect(corDoHash(hash)).toBe(corDoHash(hash));
  });

  it('ignora caixa e espaços em volta', () => {
    const cor = corDoHash('9f2ab1c4d5e6f708192a3b4c5d6e7f80');

    expect(corDoHash('  9F2AB1C4D5E6F708192A3B4C5D6E7F80 ')).toBe(cor);
  });

  it('separa hashes diferentes em cores diferentes', () => {
    const primeira = corDoHash('0000ffffffffffffffffffffffffffff');
    const segunda = corDoHash('8000ffffffffffffffffffffffffffff');

    expect(primeira).not.toBe(segunda);
  });

  it('usa a luminosidade do tema em vez de um valor fixo', () => {
    expect(corDoHash('abcdef01')).toContain('var(--luz-do-hash)');
  });

  it('mantém o matiz dentro da volta completa', () => {
    for (const hash of ['0000', 'ffff', '7fff', '4a3c']) {
      const matiz = Number(/hsl\((\d+) /.exec(corDoHash(hash))?.[1]);

      expect(matiz).toBeGreaterThanOrEqual(0);
      expect(matiz).toBeLessThanOrEqual(360);
    }
  });

  it('cai para a cor neutra quando não há hash', () => {
    expect(corDoHash('   ')).toBe('var(--c-borda-forte)');
  });
});
