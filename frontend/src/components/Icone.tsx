import type { ReactElement } from 'react';

/**
 * Conjunto de ícones desenhado à mão para este produto — sem pacote
 * externo. Todos partem da mesma grade de 24px, traço de 1.75 e pontas
 * arredondadas, para não parecerem vindos de bibliotecas diferentes.
 */
export type NomeDoIcone =
  | 'marca'
  | 'video'
  | 'arquivo'
  | 'baixar'
  | 'pacote'
  | 'copiar'
  | 'confirmado'
  | 'alerta'
  | 'informacao'
  | 'fechar'
  | 'raio'
  | 'camadas';

interface IconeProps {
  nome: NomeDoIcone;
  /** Tamanho em pixels. Padrão 16, alinhado ao texto de dado. */
  tamanho?: number;
  className?: string;
}

const TRACADOS: Record<NomeDoIcone, ReactElement> = {
  marca: (
    <>
      <rect x="3" y="3" width="12" height="12" rx="2.5" />
      <path d="M9 21h9.5A2.5 2.5 0 0 0 21 18.5V9" />
    </>
  ),
  video: (
    <>
      <rect x="2.5" y="5" width="14" height="14" rx="2.5" />
      <path d="M16.5 10.5 21.5 7.5v9l-5-3z" />
    </>
  ),
  arquivo: (
    <>
      <path d="M13.5 2.5H7A2.5 2.5 0 0 0 4.5 5v14A2.5 2.5 0 0 0 7 21.5h10a2.5 2.5 0 0 0 2.5-2.5V8.5z" />
      <path d="M13.5 2.5v6h6" />
    </>
  ),
  baixar: (
    <>
      <path d="M12 3.5v11" />
      <path d="m7.5 10.5 4.5 4.5 4.5-4.5" />
      <path d="M4 19.5h16" />
    </>
  ),
  pacote: (
    <>
      <path d="M3.5 7.5 12 3l8.5 4.5v9L12 21l-8.5-4.5z" />
      <path d="M3.5 7.5 12 12l8.5-4.5" />
      <path d="M12 12v9" />
    </>
  ),
  copiar: (
    <>
      <rect x="9" y="9" width="11.5" height="11.5" rx="2.5" />
      <path d="M6 15H5a1.5 1.5 0 0 1-1.5-1.5V5A1.5 1.5 0 0 1 5 3.5h8.5A1.5 1.5 0 0 1 15 5v1" />
    </>
  ),
  confirmado: (
    <>
      <path d="m4.5 12.5 5 5 10-11" />
    </>
  ),
  alerta: (
    <>
      <path d="M12 3.5 21.5 20h-19z" />
      <path d="M12 9.5v5" />
      <path d="M12 17.5h.01" />
    </>
  ),
  informacao: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v5.5" />
      <path d="M12 7.5h.01" />
    </>
  ),
  fechar: (
    <>
      <path d="m5.5 5.5 13 13" />
      <path d="m18.5 5.5-13 13" />
    </>
  ),
  raio: (
    <>
      <path d="M13.5 2.5 4 13.5h6.5L10 21.5 20 10.5h-6.5z" />
    </>
  ),
  camadas: (
    <>
      <path d="M12 3 3 7.5 12 12l9-4.5z" />
      <path d="m3 16.5 9 4.5 9-4.5" />
      <path d="m3 12 9 4.5L21 12" />
    </>
  ),
};

export function Icone({
  nome,
  tamanho = 16,
  className = '',
}: IconeProps): ReactElement {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      viewBox="0 0 24 24"
      width={tamanho}
      height={tamanho}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`shrink-0 ${className}`}
    >
      {TRACADOS[nome]}
    </svg>
  );
}
