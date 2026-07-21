import { useState, type ReactElement } from 'react';
import type { Job } from '../api/types.ts';
import { useCancelarJob } from '../hooks/useCancelarJob.ts';
import { mensagemDeErro } from '../lib/erro.ts';
import { descricaoDoModo, rotuloDasSaidas } from '../lib/modos.ts';
import { Alerta } from './Alerta.tsx';
import { Botao } from './Botao.tsx';
import { DialogoDeConfirmacao } from './DialogoDeConfirmacao.tsx';
import { Icone } from './Icone.tsx';
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
  const instantaneo = descricaoDoModo(job.mode).rapido;

  function confirmarCancelamento(): void {
    cancelamento.mutate(undefined, {
      onSuccess: () => setConfirmandoCancelamento(false),
      onError: () => setConfirmandoCancelamento(false),
    });
  }

  return (
    <section className="flex flex-col gap-5 animate-surgir">
      <header
        className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3"
      >
        <div className="min-w-0">
          <p className="font-mono text-selo uppercase text-destaque">
            02 · Processando
          </p>

          <h1
            className="mt-1.5 font-mono text-titulo font-semibold text-texto
                       sm:text-secao"
          >
            {instantaneo ? 'Preparando suas cópias' : 'Gerando suas variações'}
          </h1>

          <p className="mt-1.5 max-w-prose text-nota text-texto-suave">
            {instantaneo
              ? 'Isso leva menos de um segundo. Os arquivos aparecem aqui em ' +
                'seguida.'
              : 'Pode deixar esta página aberta. Atualizamos o progresso ' +
                'sozinhos.'}
          </p>
        </div>

        <Botao
          variante="perigo"
          tamanho="compacto"
          onClick={() => setConfirmandoCancelamento(true)}
          icone={<Icone nome="fechar" tamanho={13} />}
        >
          Cancelar geração
        </Botao>
      </header>

      <ResumoDoProgresso job={job} mostrarBarra={!instantaneo} />

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

      <PainelDeVariacoes
        jobId={job.job_id}
        statusDoJob={job.status}
        modo={job.mode}
        variacoes={job.variations}
        mensagemVazia={`As ${rotuloDasSaidas(job.mode)} aparecem aqui assim
                        que ficarem prontas.`}
      />

      {confirmandoCancelamento ? (
        <DialogoDeConfirmacao
          titulo="Cancelar a geração?"
          descricao={`As ${rotuloDasSaidas(job.mode)} que ainda não ficaram
                      prontas serão descartadas. Isso não pode ser desfeito.`}
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
