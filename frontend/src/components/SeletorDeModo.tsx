import { useId, type ReactElement } from 'react';
import type { ProcessingMode } from '../api/types.ts';
import { MODOS, type DescricaoDeModo } from '../lib/modos.ts';
import { Icone } from './Icone.tsx';

interface SeletorDeModoProps {
  valor: ProcessingMode;
  desabilitado: boolean;
  aoMudar: (modo: ProcessingMode) => void;
}

/**
 * Escolha do modo de processamento. Radio group real (fieldset + legend +
 * input[type=radio]), para funcionar com teclado e leitor de tela sem
 * ARIA improvisado.
 */
export function SeletorDeModo({
  valor,
  desabilitado,
  aoMudar,
}: SeletorDeModoProps): ReactElement {
  const nomeDoGrupo = useId();

  return (
    <fieldset className="m-0 min-w-0 border-0 p-0" disabled={desabilitado}>
      <legend className="mb-2 text-nota font-semibold text-texto">
        O que você quer fazer com o vídeo?
      </legend>

      <div className="flex flex-col gap-2">
        {MODOS.map((opcao) => (
          <OpcaoDeModo
            key={opcao.modo}
            nomeDoGrupo={nomeDoGrupo}
            opcao={opcao}
            selecionado={valor === opcao.modo}
            aoSelecionar={() => aoMudar(opcao.modo)}
          />
        ))}
      </div>
    </fieldset>
  );
}

interface OpcaoDeModoProps {
  nomeDoGrupo: string;
  opcao: DescricaoDeModo;
  selecionado: boolean;
  aoSelecionar: () => void;
}

function OpcaoDeModo({
  nomeDoGrupo,
  opcao,
  selecionado,
  aoSelecionar,
}: OpcaoDeModoProps): ReactElement {
  const estiloDoCartao = selecionado
    ? 'border-destaque bg-destaque-suave'
    : 'border-borda bg-superficie hover:border-borda-forte';

  const estiloDaEtiqueta = opcao.rapido
    ? 'border-sucesso/40 bg-sucesso-suave text-sucesso'
    : 'border-borda bg-superficie-suave text-texto-suave';

  return (
    <label
      className={`flex cursor-pointer items-start gap-3 rounded-xl border p-3
                  transition-colors has-[:focus-visible]:outline
                  has-[:focus-visible]:outline-2
                  has-[:focus-visible]:outline-destaque
                  has-[:focus-visible]:outline-offset-2 ${estiloDoCartao}`}
    >
      <input
        type="radio"
        name={nomeDoGrupo}
        value={opcao.modo}
        checked={selecionado}
        onChange={aoSelecionar}
        className="mt-1 size-4 shrink-0 accent-destaque"
      />

      <span className="flex min-w-0 flex-col gap-1">
        <span className="flex flex-wrap items-center gap-2">
          <span className="text-nota font-semibold text-texto">
            {opcao.titulo}
          </span>

          <span
            className={`inline-flex items-center gap-1 rounded-md border
                        px-1.5 py-0.5 font-mono text-selo font-semibold
                        ${estiloDaEtiqueta}`}
          >
            {opcao.rapido ? <Icone nome="raio" tamanho={11} /> : null}
            {opcao.etiquetaDeTempo}
          </span>
        </span>

        <span className="text-micro text-texto-suave">{opcao.descricao}</span>
      </span>
    </label>
  );
}
