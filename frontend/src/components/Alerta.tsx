import type { ReactElement } from 'react';
import { Botao } from './Botao.tsx';
import { Icone, type NomeDoIcone } from './Icone.tsx';

export type TomDoAlerta = 'erro' | 'aviso' | 'informacao' | 'sucesso';

interface AlertaProps {
  tom?: TomDoAlerta;
  titulo: string;
  mensagem: string;
  rotuloDaAcao?: string;
  aoAcionar?: () => void;
  acaoCarregando?: boolean;
}

/**
 * A faixa colorida à esquerda dá o tom antes da leitura; o ícone e o texto
 * repetem a informação, para quem não distingue as cores.
 */
const ESTILO_POR_TOM: Record<TomDoAlerta, string> = {
  erro: 'border-erro/40 bg-erro-suave before:bg-erro',
  aviso: 'border-alerta/40 bg-alerta-suave before:bg-alerta',
  informacao: 'border-borda bg-superficie before:bg-borda-forte',
  sucesso: 'border-sucesso/40 bg-sucesso-suave before:bg-sucesso',
};

const COR_DO_ICONE: Record<TomDoAlerta, string> = {
  erro: 'text-erro',
  aviso: 'text-alerta',
  informacao: 'text-texto-fraco',
  sucesso: 'text-sucesso',
};

const ICONE_POR_TOM: Record<TomDoAlerta, NomeDoIcone> = {
  erro: 'alerta',
  aviso: 'alerta',
  informacao: 'informacao',
  sucesso: 'confirmado',
};

export function Alerta({
  tom = 'erro',
  titulo,
  mensagem,
  rotuloDaAcao,
  aoAcionar,
  acaoCarregando = false,
}: AlertaProps): ReactElement {
  return (
    <div
      role={tom === 'erro' ? 'alert' : 'status'}
      className={`relative flex flex-col gap-3 overflow-hidden rounded-xl
                  border py-3 pr-4 pl-5 sm:flex-row sm:items-center
                  sm:justify-between sm:gap-4
                  before:absolute before:inset-y-0 before:left-0 before:w-1
                  before:content-[''] ${ESTILO_POR_TOM[tom]}`}
    >
      <div className="flex min-w-0 items-start gap-2.5">
        <span className={`mt-0.5 ${COR_DO_ICONE[tom]}`}>
          <Icone nome={ICONE_POR_TOM[tom]} tamanho={16} />
        </span>

        <div className="min-w-0">
          <p className="text-nota font-semibold text-texto">{titulo}</p>
          <p className="mt-0.5 text-nota break-words text-texto-suave">
            {mensagem}
          </p>
        </div>
      </div>

      {rotuloDaAcao !== undefined && aoAcionar !== undefined ? (
        <Botao
          variante="secundario"
          tamanho="compacto"
          onClick={aoAcionar}
          carregando={acaoCarregando}
          className="shrink-0 self-start sm:self-auto"
        >
          {rotuloDaAcao}
        </Botao>
      ) : null}
    </div>
  );
}
