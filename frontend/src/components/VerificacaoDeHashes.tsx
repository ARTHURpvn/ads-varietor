import type { ReactElement } from 'react';
import type { ProcessingMode, Variation } from '../api/types.ts';
import { analisarHashes } from '../lib/hash.ts';
import { mensagemDaVerificacaoDeHashes } from '../lib/mensagens.ts';
import { Alerta } from './Alerta.tsx';

interface VerificacaoDeHashesProps {
  variacoes: readonly Variation[];
  /** MD5 do arquivo enviado pelo usuário. */
  hashDeOrigem: string | null;
  modo: ProcessingMode;
}

/**
 * Confirma — ou desmente — a promessa do produto: todo arquivo gerado tem
 * identificação diferente das outras e do original. Some quando nenhum
 * hash chegou da API, para não afirmar o que não foi conferido.
 */
export function VerificacaoDeHashes({
  variacoes,
  hashDeOrigem,
  modo,
}: VerificacaoDeHashesProps): ReactElement | null {
  const prontas = variacoes.filter(
    (variacao) => variacao.status === 'completed',
  );

  const analise = analisarHashes(
    prontas.map((variacao) => variacao.md5),
    hashDeOrigem,
  );

  if (analise.comHash === 0) {
    return null;
  }

  return (
    <Alerta
      tom={analise.tudoDistinto ? 'sucesso' : 'aviso'}
      titulo={
        analise.tudoDistinto
          ? 'Cada arquivo ficou com uma identificação única'
          : 'Encontramos arquivos com a mesma identificação'
      }
      mensagem={mensagemDaVerificacaoDeHashes(analise, modo)}
    />
  );
}
