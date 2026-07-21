import type { ReactElement } from 'react';
import {
  rotuloDoStatusDaVariacao,
  type StatusExibidoDaVariacao,
} from '../lib/mensagens.ts';

interface SeloDeStatusProps {
  status: StatusExibidoDaVariacao;
}

/**
 * Etiqueta de status de uma saída. Cor + ponto + palavra: quem não
 * distingue as cores continua lendo o estado.
 */
const ESTILO_POR_STATUS: Record<StatusExibidoDaVariacao, string> = {
  pending: 'border-borda bg-superficie-suave text-texto-fraco',
  running: 'border-destaque/40 bg-destaque-suave text-destaque',
  completed: 'border-sucesso/40 bg-sucesso-suave text-sucesso',
  failed: 'border-erro/40 bg-erro-suave text-erro',
  interrompida: 'border-alerta/40 bg-alerta-suave text-alerta',
};

export function SeloDeStatus({ status }: SeloDeStatusProps): ReactElement {
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1.5 rounded-md border
                  px-1.5 py-0.5 font-mono text-selo font-semibold uppercase
                  ${ESTILO_POR_STATUS[status]}`}
    >
      <span
        aria-hidden="true"
        className={`size-1.5 rounded-full bg-current
                    ${status === 'running' ? 'animate-pulsar' : ''}`}
      />
      {rotuloDoStatusDaVariacao(status)}
    </span>
  );
}
