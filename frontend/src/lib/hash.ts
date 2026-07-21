/**
 * Tratamento dos hashes MD5 devolvidos pela API.
 *
 * O produto só cumpre a promessa se cada arquivo gerado tiver um hash
 * diferente dos demais E diferente do original. Aqui ficam a conferência
 * dessa promessa e o encurtamento para caber em telas estreitas.
 */

/** Caracteres mostrados de cada ponta ao encurtar um hash. */
const CARACTERES_VISIVEIS = 8;

/**
 * Normaliza para comparação: hash vazio ou ausente vira `null`, o resto
 * vira minúsculo sem espaços. Sem isto, o mesmo hash em caixas diferentes
 * passaria despercebido como duplicata.
 */
export function normalizarHash(hash: string | null | undefined): string | null {
  if (hash === null || hash === undefined) {
    return null;
  }

  const limpo = hash.trim().toLowerCase();
  return limpo.length === 0 ? null : limpo;
}

/**
 * Encurta para `inicio…fim`. Hashes curtos o bastante voltam inteiros —
 * encurtar nesse caso só tiraria informação sem ganhar espaço.
 */
export function encurtarHash(
  hash: string,
  visiveis: number = CARACTERES_VISIVEIS,
): string {
  if (visiveis <= 0 || hash.length <= visiveis * 2 + 1) {
    return hash;
  }

  return `${hash.slice(0, visiveis)}…${hash.slice(-visiveis)}`;
}

export interface AnaliseDeHashes {
  /** Quantos arquivos têm hash conhecido. */
  comHash: number;
  /** Quantos ainda não têm hash registrado pela API. */
  semHash: number;
  /** Hashes que aparecem em mais de um arquivo gerado. */
  duplicados: readonly string[];
  /** Quantos arquivos gerados repetem o hash do original. */
  repetemOOriginal: number;
  /** true quando há hashes e nenhum deles se repete nem bate com o original. */
  tudoDistinto: boolean;
}

/**
 * Confere a unicidade dos hashes gerados contra o hash de origem.
 * Entradas sem hash são contadas à parte, nunca tratadas como iguais.
 */
export function analisarHashes(
  hashes: readonly (string | null | undefined)[],
  hashDeOrigem: string | null | undefined,
): AnaliseDeHashes {
  const origem = normalizarHash(hashDeOrigem);
  const conhecidos: string[] = [];
  let semHash = 0;

  for (const bruto of hashes) {
    const normalizado = normalizarHash(bruto);

    if (normalizado === null) {
      semHash += 1;
      continue;
    }

    conhecidos.push(normalizado);
  }

  const ocorrencias = new Map<string, number>();

  for (const hash of conhecidos) {
    ocorrencias.set(hash, (ocorrencias.get(hash) ?? 0) + 1);
  }

  const duplicados = [...ocorrencias.entries()]
    .filter(([, quantidade]) => quantidade > 1)
    .map(([hash]) => hash);

  const repetemOOriginal =
    origem === null
      ? 0
      : conhecidos.filter((hash) => hash === origem).length;

  return {
    comHash: conhecidos.length,
    semHash,
    duplicados,
    repetemOOriginal,
    tudoDistinto:
      conhecidos.length > 0 &&
      duplicados.length === 0 &&
      repetemOOriginal === 0,
  };
}
