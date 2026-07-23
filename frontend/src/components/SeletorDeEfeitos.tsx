import { useId, type ReactElement } from 'react';
import type { SelecaoDeEfeitos } from '../api/jobs.ts';

interface EfeitoDescrito {
  chave: keyof SelecaoDeEfeitos;
  titulo: string;
  descricao: string;
}

/** As quatro famílias de efeito que o motor sabe variar, em linguagem de
 *  usuário — nada de "filtergraph" ou "colorize". */
const EFEITOS: readonly EfeitoDescrito[] = [
  {
    chave: 'color',
    titulo: 'Cor',
    descricao: 'Brilho, contraste, saturação ou matiz levemente diferentes.',
  },
  {
    chave: 'framing',
    titulo: 'Enquadramento',
    descricao: 'Um zoom discreto que muda o corte sem perder resolução.',
  },
  {
    chave: 'speed',
    titulo: 'Velocidade',
    descricao: 'Acelera de forma quase imperceptível, entre 1,00x e 1,05x.',
  },
  {
    chave: 'noise',
    titulo: 'Ruído no áudio',
    descricao: 'Um chiado inaudível no fundo, para mudar a faixa de som.',
  },
];

interface SeletorDeEfeitosProps {
  valor: SelecaoDeEfeitos;
  desabilitado?: boolean;
  aoMudar: (valor: SelecaoDeEfeitos) => void;
}

/**
 * Deixa o usuário escolher o que muda em cada cópia. A identidade do arquivo
 * (hash e metadados) muda sempre e por isso não aparece aqui — não é opcional.
 */
export function SeletorDeEfeitos({
  valor,
  desabilitado = false,
  aoMudar,
}: SeletorDeEfeitosProps): ReactElement {
  const grupoId = useId();
  const nenhumSelecionado = !EFEITOS.some((efeito) => valor[efeito.chave]);

  return (
    <fieldset
      className="flex flex-col gap-3"
      aria-describedby={`${grupoId}-ajuda`}
    >
      <div className="flex flex-col gap-1">
        <legend className="text-nota font-semibold text-texto">
          O que você quer variar?
        </legend>
        <p id={`${grupoId}-ajuda`} className="text-micro text-texto-fraco">
          A identificação interna do arquivo muda sempre. Escolha abaixo o que
          mais deve mudar na imagem e no som.
        </p>
      </div>

      <div className="grid gap-2 sm:grid-cols-2">
        {EFEITOS.map((efeito) => {
          const ligado = valor[efeito.chave];
          return (
            <label
              key={efeito.chave}
              className={`flex cursor-pointer gap-3 rounded-xl border p-3
                          transition-colors
                          has-[:focus-visible]:ring-2
                          has-[:focus-visible]:ring-destaque
                          ${
                            ligado
                              ? 'border-destaque bg-destaque-suave'
                              : 'border-borda bg-superficie ' +
                                'hover:border-borda-forte'
                          }
                          ${desabilitado ? 'cursor-not-allowed opacity-55' : ''}`}
            >
              <input
                type="checkbox"
                checked={ligado}
                disabled={desabilitado}
                onChange={(evento) =>
                  aoMudar({ ...valor, [efeito.chave]: evento.target.checked })
                }
                className="mt-0.5 size-4 shrink-0 accent-destaque"
              />
              <span className="flex flex-col gap-0.5">
                <span className="text-nota font-semibold text-texto">
                  {efeito.titulo}
                </span>
                <span className="text-micro text-texto-suave">
                  {efeito.descricao}
                </span>
              </span>
            </label>
          );
        })}
      </div>

      {nenhumSelecionado ? (
        <p
          role="alert"
          className="text-micro font-medium text-alerta"
        >
          Sem nenhum efeito, a imagem fica idêntica ao original — use o modo
          que só troca a identidade do arquivo, que é bem mais rápido.
        </p>
      ) : null}
    </fieldset>
  );
}
