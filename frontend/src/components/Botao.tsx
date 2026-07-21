import type { ComponentPropsWithRef, ReactElement, ReactNode } from 'react';

export type VarianteDeBotao =
  | 'primario'
  | 'secundario'
  | 'discreto'
  | 'perigo';

export type TamanhoDeBotao = 'normal' | 'compacto';

interface BotaoProps extends ComponentPropsWithRef<'button'> {
  variante?: VarianteDeBotao;
  tamanho?: TamanhoDeBotao;
  carregando?: boolean;
  /** Ícone à esquerda do rótulo. Some enquanto o botão carrega. */
  icone?: ReactNode;
  children: ReactNode;
}

const ESTILO_BASE =
  'inline-flex items-center justify-center gap-2 rounded-lg font-semibold ' +
  'transition-[background-color,border-color,color,transform] duration-150 ' +
  'active:translate-y-px disabled:cursor-not-allowed disabled:opacity-45 ' +
  'disabled:active:translate-y-0';

const ESTILO_POR_TAMANHO: Record<TamanhoDeBotao, string> = {
  normal: 'min-h-11 px-4 py-2.5 text-nota',
  compacto: 'min-h-9 px-3 py-1.5 text-micro',
};

const ESTILO_POR_VARIANTE: Record<VarianteDeBotao, string> = {
  primario:
    'bg-destaque text-sobre-destaque hover:bg-destaque-forte ' +
    'shadow-[var(--sombra-cartao)]',
  secundario:
    'border border-borda-forte bg-superficie text-texto ' +
    'hover:border-destaque hover:text-destaque',
  discreto:
    'border border-transparent text-texto-suave ' +
    'hover:bg-superficie-suave hover:text-texto',
  perigo:
    'border border-erro/50 bg-transparent text-erro ' +
    'hover:border-erro hover:bg-erro-suave',
};

export function Botao({
  variante = 'primario',
  tamanho = 'normal',
  carregando = false,
  disabled = false,
  icone,
  children,
  className = '',
  type = 'button',
  ...resto
}: BotaoProps): ReactElement {
  return (
    <button
      {...resto}
      type={type}
      disabled={disabled || carregando}
      aria-busy={carregando}
      className={`${ESTILO_BASE} ${ESTILO_POR_TAMANHO[tamanho]}
                  ${ESTILO_POR_VARIANTE[variante]} ${className}`}
    >
      {carregando ? <Girador /> : icone}
      <span>{children}</span>
    </button>
  );
}

function Girador(): ReactElement {
  return (
    <span
      aria-hidden="true"
      className="size-4 animate-spin rounded-full border-2 border-current
                 border-t-transparent"
    />
  );
}
