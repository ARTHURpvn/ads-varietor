import type { ComponentPropsWithRef, ReactElement, ReactNode } from 'react';

export type VarianteDeBotao = 'primario' | 'secundario' | 'perigo';

interface BotaoProps extends ComponentPropsWithRef<'button'> {
  variante?: VarianteDeBotao;
  carregando?: boolean;
  children: ReactNode;
}

const ESTILO_BASE =
  'inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 ' +
  'text-sm font-semibold transition-colors disabled:cursor-not-allowed ' +
  'disabled:opacity-50 min-h-11';

const ESTILO_POR_VARIANTE: Record<VarianteDeBotao, string> = {
  primario:
    'bg-destaque text-[#08111f] hover:bg-destaque-forte hover:text-white',
  secundario:
    'bg-superficie-suave text-texto border border-borda hover:bg-borda',
  perigo: 'bg-transparent text-erro border border-erro/60 hover:bg-erro/10',
};

export function Botao({
  variante = 'primario',
  carregando = false,
  disabled = false,
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
      className={`${ESTILO_BASE} ${ESTILO_POR_VARIANTE[variante]} ${className}`}
    >
      {carregando ? <Girador /> : null}
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
