import { useCallback, useState, type ReactElement } from 'react';
import { isTerminalStatus } from './api/types.ts';
import { Alerta } from './components/Alerta.tsx';
import { Botao } from './components/Botao.tsx';
import { TelaDeCarregamento } from './components/TelaDeCarregamento.tsx';
import { TelaDeEnvio } from './components/TelaDeEnvio.tsx';
import { TelaDeProgresso } from './components/TelaDeProgresso.tsx';
import { TelaDeResultados } from './components/TelaDeResultados.tsx';
import { useCriarJob } from './hooks/useCriarJob.ts';
import { useJob } from './hooks/useJob.ts';
import { useJobArmazenado } from './hooks/useJobArmazenado.ts';
import { mensagemDeErro, tituloDeErro } from './lib/erro.ts';

export function App(): ReactElement {
  const { jobIdSalvo, salvarJobId, limparJobId } = useJobArmazenado();
  const [jobIdAtivo, setJobIdAtivo] = useState<string | null>(null);

  const criacao = useCriarJob((job) => {
    salvarJobId(job.job_id);
    setJobIdAtivo(job.job_id);
  });

  const consulta = useJob(jobIdAtivo);

  const voltarParaOEnvio = useCallback((): void => {
    setJobIdAtivo(null);
    limparJobId();
    criacao.reset();
  }, [criacao, limparJobId]);

  return (
    <div className="min-h-screen">
      <main className="mx-auto w-full max-w-3xl px-4 py-8 sm:px-6 sm:py-12">
        {renderizarEtapa()}
      </main>
    </div>
  );

  function renderizarEtapa(): ReactElement {
    if (jobIdAtivo === null) {
      return (
        <TelaDeEnvio
          enviando={criacao.isPending}
          erroDoEnvio={criacao.isError ? mensagemDeErro(criacao.error) : null}
          aoLimparErroDoEnvio={criacao.reset}
          aoEnviar={(arquivo, numeroDeVariacoes) =>
            criacao.mutate({ file: arquivo, numVariations: numeroDeVariacoes })
          }
          {...(jobIdSalvo !== null
            ? {
                jobSalvo: {
                  jobId: jobIdSalvo,
                  aoRetomar: () => setJobIdAtivo(jobIdSalvo),
                  aoDescartar: limparJobId,
                },
              }
            : {})}
        />
      );
    }

    const job = consulta.data;

    if (job === undefined && consulta.isError) {
      return (
        <div className="flex flex-col gap-4">
          <Alerta
            tom="erro"
            titulo={tituloDeErro(consulta.error)}
            mensagem={mensagemDeErro(consulta.error)}
            rotuloDaAcao="Tentar de novo"
            aoAcionar={() => void consulta.refetch()}
            acaoCarregando={consulta.isFetching}
          />

          <Botao variante="secundario" onClick={voltarParaOEnvio}>
            Enviar outro vídeo
          </Botao>
        </div>
      );
    }

    if (job === undefined) {
      return (
        <TelaDeCarregamento mensagem="Carregando o andamento do seu vídeo..." />
      );
    }

    if (isTerminalStatus(job.status)) {
      return (
        <TelaDeResultados job={job} aoComecarDeNovo={voltarParaOEnvio} />
      );
    }

    return (
      <TelaDeProgresso
        job={job}
        avisoDeConexao={
          consulta.isError
            ? 'Estamos com dificuldade para atualizar o progresso. ' +
              'Continuamos tentando automaticamente.'
            : null
        }
      />
    );
  }
}
