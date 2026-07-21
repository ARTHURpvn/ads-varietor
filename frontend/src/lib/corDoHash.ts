/**
 * Cor estável derivada da identificação (MD5) de um arquivo gerado.
 *
 * Motivo: numa grade de 50 saídas todos os cartões dizem a mesma coisa. A
 * cor dá a cada arquivo uma identidade visual imediata, e faz duplicatas
 * saltarem aos olhos — dois arquivos com a mesma identificação recebem
 * exatamente a mesma cor.
 *
 * A cor é decorativa: nunca é o único portador de informação. O hash em
 * texto continua ao lado dela, e o status continua escrito por extenso.
 */

/** Quantos caracteres do hash alimentam o matiz. */
const DIGITOS_DE_MATIZ = 4;
const MAXIMO_DE_MATIZ = 0x10000;

/** Saturação base e passo, para separar hashes de matiz parecido. */
const SATURACAO_BASE = 52;
const PASSO_DE_SATURACAO = 9;
const NIVEIS_DE_SATURACAO = 4;

/**
 * Devolve uma cor CSS `hsl(...)` determinística para o hash informado.
 * A luminosidade vem da variável `--luz-do-hash`, que muda entre o tema
 * claro e o escuro para manter a cor legível nos dois.
 */
export function corDoHash(hash: string): string {
  const limpo = hash.trim().toLowerCase();

  if (limpo.length === 0) {
    return 'var(--c-borda-forte)';
  }

  const matiz = matizDoHash(limpo);
  const saturacao = saturacaoDoHash(limpo);

  return `hsl(${matiz} ${saturacao}% var(--luz-do-hash))`;
}

function matizDoHash(hash: string): number {
  const bruto = Number.parseInt(hash.slice(0, DIGITOS_DE_MATIZ), 16);

  if (!Number.isFinite(bruto)) {
    return 0;
  }

  return Math.round((bruto / MAXIMO_DE_MATIZ) * 360);
}

function saturacaoDoHash(hash: string): number {
  const digito = hash.slice(DIGITOS_DE_MATIZ, DIGITOS_DE_MATIZ + 1);
  const bruto = Number.parseInt(digito, 16);
  const nivel = Number.isFinite(bruto) ? bruto % NIVEIS_DE_SATURACAO : 0;

  return SATURACAO_BASE + nivel * PASSO_DE_SATURACAO;
}
