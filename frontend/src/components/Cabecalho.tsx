import type { ReactElement } from 'react';
import { Icone } from './Icone.tsx';

/** Etapas do fluxo, na ordem em que acontecem. */
export type EtapaDoFluxo = 'envio' | 'processando' | 'resultado';

interface CabecalhoProps {
  etapa: EtapaDoFluxo;
}

interface DescricaoDeEtapa {
  etapa: EtapaDoFluxo;
  numero: string;
  rotulo: string;
}

/**
 * A numeração aqui não é enfeite: o fluxo é mesmo sequencial e o usuário
 * precisa saber em que ponto dele está.
 */
const ETAPAS: readonly DescricaoDeEtapa[] = [
  { etapa: 'envio', numero: '01', rotulo: 'Envio' },
  { etapa: 'processando', numero: '02', rotulo: 'Processando' },
  { etapa: 'resultado', numero: '03', rotulo: 'Resultado' },
];

export function Cabecalho({ etapa }: CabecalhoProps): ReactElement {
  const posicaoAtual = ETAPAS.findIndex((item) => item.etapa === etapa);

  return (
    <header
      className="sticky top-0 z-30 border-b border-borda
                 bg-fundo/95 backdrop-blur-md"
    >
      <div
        className="mx-auto flex h-14 w-full max-w-6xl items-center gap-3
                   px-4 sm:px-6"
      >
        <span
          className="flex size-8 shrink-0 items-center justify-center
                     rounded-lg bg-destaque text-sobre-destaque"
        >
          <Icone nome="marca" tamanho={17} />
        </span>

        {/*
          `truncate` é obrigatório junto com `min-w-0`: sem ele o texto
          escapa da caixa encolhida e é desenhado por cima dos chips de
          etapa em telas de 320–375px.
        */}
        <p
          className="min-w-0 truncate font-mono text-nota font-semibold
                     text-texto"
        >
          variações
          <span className="text-destaque">/</span>
          <span className="text-texto-fraco">vídeo</span>
        </p>

        {/* `shrink-0`: as etapas nunca cedem espaço para a marca. */}
        <ol
          aria-label="Etapas do fluxo"
          className="ml-auto flex shrink-0 items-center gap-1 sm:gap-1.5"
        >
          {ETAPAS.map((item, indice) => (
            <PassoDoFluxo
              key={item.etapa}
              descricao={item}
              estado={
                indice < posicaoAtual
                  ? 'concluido'
                  : indice === posicaoAtual
                    ? 'atual'
                    : 'futuro'
              }
            />
          ))}
        </ol>
      </div>
    </header>
  );
}

type EstadoDoPasso = 'concluido' | 'atual' | 'futuro';

interface PassoDoFluxoProps {
  descricao: DescricaoDeEtapa;
  estado: EstadoDoPasso;
}

const ESTILO_POR_ESTADO: Record<EstadoDoPasso, string> = {
  concluido: 'border-borda text-texto-suave',
  atual: 'border-destaque bg-destaque-suave text-destaque',
  futuro: 'border-transparent text-texto-fraco',
};

function PassoDoFluxo({
  descricao,
  estado,
}: PassoDoFluxoProps): ReactElement {
  return (
    <li
      aria-current={estado === 'atual' ? 'step' : undefined}
      className={`flex items-center gap-1.5 rounded-lg border px-2 py-1
                  font-mono text-selo uppercase transition-colors
                  ${ESTILO_POR_ESTADO[estado]}`}
    >
      {estado === 'concluido' ? (
        <Icone nome="confirmado" tamanho={11} className="text-sucesso" />
      ) : (
        <span aria-hidden="true">{descricao.numero}</span>
      )}

      <span className={estado === 'atual' ? '' : 'sr-only sm:not-sr-only'}>
        {descricao.rotulo}
      </span>
    </li>
  );
}
