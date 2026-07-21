import { useState, type ReactElement } from 'react';
import type { Job } from '../api/types.ts';
import { useCancelarJob } from '../hooks/useCancelarJob.ts';
import { mensagemDeErro } from '../lib/erro.ts';
import { Alerta } from './Alerta.tsx';
import { Botao } from './Botao.tsx';
import { DialogoDeConfirmacao } from './DialogoDeConfirmacao.tsx';
import { PainelDeVariacoes } from './PainelDeVariacoes.tsx';
import { ResumoDoProgresso } from './ResumoDoProgresso.tsx';

interface TelaDeProgressoProps {
  job: Job;
  /** Aviso de conexão instável durante o acompanhamento. */
  avisoDeConexao: string | null;
}

export function TelaDeProgresso({
  job,
  avisoDeConexao,
}: TelaDeProgressoProps): ReactElement {
  const [confirmandoCancelamento, setConfirmandoCancelamento] =
    useState(false);
  const cancelamento = useCancelarJob(job.job_id);

  function confirmarCancelamento(): void {
    cancelamento.mutate(undefined, {
      onSuccess: () => setConfirmandoCancelamento(false),
      onError: () => setConfirmandoCancelamento(false),
    });
  }

  return (
    <section className="flex flex-col gap-6">
      <header>
        <h1 className="text-2xl font-bold text-texto sm:text-3xl">
          Gerando suas variações
        </h1>
        <p className="mt-2 text-sm text-texto-suave">
          Pode deixar esta página aberta. Atualizamos o progresso sozinhos.
        </p>
      </header>

      <ResumoDoProgresso job={job} />

      {avisoDeConexao !== null ? (
        <Alerta
          tom="aviso"
          titulo="Conexão instável"
          mensagem={avisoDeConexao}
        />
      ) : null}

      {cancelamento.isError ? (
        <Alerta
          tom="erro"
          titulo="Não deu para cancelar"
          mensagem={mensagemDeErro(cancelamento.error)}
        />
      ) : null}

      <Botao
        variante="perigo"
        onClick={() => setConfirmandoCancelamento(true)}
        className="self-start"
      >
        Cancelar geração
      </Botao>

      <PainelDeVariacoes
        jobId={job.job_id}
        statusDoJob={job.status}
        variacoes={job.variations}
        mensagemVazia="As variações aparecem aqui assim que começarem a ser
                       geradas."
      />

      {confirmandoCancelamento ? (
        <DialogoDeConfirmacao
          titulo="Cancelar a geração?"
          descricao="As variações que ainda não ficaram prontas serão
                     descartadas. Isso não pode ser desfeito."
          rotuloConfirmar="Sim, cancelar"
          rotuloCancelar="Continuar gerando"
          confirmando={cancelamento.isPending}
          aoConfirmar={confirmarCancelamento}
          aoCancelar={() => setConfirmandoCancelamento(false)}
        />
      ) : null}
    </section>
  );
}
