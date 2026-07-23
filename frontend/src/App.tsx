import { useCallback, useState, type ReactElement } from 'react';
import { isTerminalStatus } from './api/types.ts';
import { Alerta } from './components/Alerta.tsx';
import { Botao } from './components/Botao.tsx';
import { Cabecalho, type EtapaDoFluxo } from './components/Cabecalho.tsx';
import { TelaDeCarregamento } from './components/TelaDeCarregamento.tsx';
import { TelaDeEnvio } from './components/TelaDeEnvio.tsx';
import { TelaDeProgresso } from './components/TelaDeProgresso.tsx';
import { TelaDeResultados } from './components/TelaDeResultados.tsx';
import { useCriarJob } from './hooks/useCriarJob.ts';
import { useJob } from './hooks/useJob.ts';
import { useJobArmazenado } from './hooks/useJobArmazenado.ts';
import { mensagemDeErro, tituloDeErro } from './lib/erro.ts';

/**
 * A largura útil acompanha a densidade da etapa: o formulário é uma coluna
 * só e fica ilegível esticado; a grade de resultados precisa de espaço
 * para caber quatro colunas de cartão.
 */
const LARGURA_POR_ETAPA: Record<EtapaDoFluxo, string> = {
  envio: 'max-w-2xl',
  processando: 'max-w-5xl',
  resultado: 'max-w-6xl',
};

interface EtapaRenderizada {
  etapa: EtapaDoFluxo;
  conteudo: ReactElement;
}

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

  const { etapa, conteudo } = renderizarEtapa();

  return (
    <div className="flex min-h-screen flex-col">
      <Cabecalho etapa={etapa} />

      <main
        className={`mx-auto w-full flex-1 px-4 py-6 sm:px-6 sm:py-10
                    ${LARGURA_POR_ETAPA[etapa]}`}
      >
        {conteudo}
      </main>
    </div>
  );

  function renderizarEtapa(): EtapaRenderizada {
    if (jobIdAtivo === null) {
      return {
        etapa: 'envio',
        conteudo: (
          <TelaDeEnvio
            enviando={criacao.isPending}
            erroDoEnvio={
              criacao.isError ? mensagemDeErro(criacao.error) : null
            }
            aoLimparErroDoEnvio={criacao.reset}
            aoEnviar={(arquivo, numeroDeVariacoes, modo, efeitos) =>
              criacao.mutate({
                file: arquivo,
                numVariations: numeroDeVariacoes,
                mode: modo,
                efeitos,
              })
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
        ),
      };
    }

    const job = consulta.data;

    if (job === undefined && consulta.isError) {
      return {
        etapa: 'processando',
        conteudo: (
          <div className="flex flex-col gap-3">
            <Alerta
              tom="erro"
              titulo={tituloDeErro(consulta.error)}
              mensagem={mensagemDeErro(consulta.error)}
              rotuloDaAcao="Tentar de novo"
              aoAcionar={() => void consulta.refetch()}
              acaoCarregando={consulta.isFetching}
            />

            <Botao
              variante="secundario"
              onClick={voltarParaOEnvio}
              className="self-start"
            >
              Enviar outro vídeo
            </Botao>
          </div>
        ),
      };
    }

    if (job === undefined) {
      return {
        etapa: 'processando',
        conteudo: (
          <TelaDeCarregamento mensagem="Carregando o andamento do seu vídeo..." />
        ),
      };
    }

    if (isTerminalStatus(job.status)) {
      return {
        etapa: 'resultado',
        conteudo: (
          <TelaDeResultados job={job} aoComecarDeNovo={voltarParaOEnvio} />
        ),
      };
    }

    return {
      etapa: 'processando',
      conteudo: (
        <TelaDeProgresso
          job={job}
          avisoDeConexao={
            consulta.isError
              ? 'Estamos com dificuldade para atualizar o progresso. ' +
                'Continuamos tentando automaticamente.'
              : null
          }
        />
      ),
    };
  }
}
