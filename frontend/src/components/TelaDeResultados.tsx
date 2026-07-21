import type { ReactElement } from 'react';
import type { Job } from '../api/types.ts';
import { useDownloadDoZip } from '../hooks/useDownloads.ts';
import { mensagemDeErro } from '../lib/erro.ts';
import { motivoDaFalhaDoJob, rotuloDoStatusDoJob } from '../lib/mensagens.ts';
import { Alerta } from './Alerta.tsx';
import { Botao } from './Botao.tsx';
import { PainelDeVariacoes } from './PainelDeVariacoes.tsx';

interface TelaDeResultadosProps {
  job: Job;
  aoComecarDeNovo: () => void;
}

export function TelaDeResultados({
  job,
  aoComecarDeNovo,
}: TelaDeResultadosProps): ReactElement {
  const downloadDoZip = useDownloadDoZip();

  const prontas = job.variations.filter(
    (variacao) => variacao.status === 'completed',
  ).length;
  const comFalha = job.variations.filter(
    (variacao) => variacao.status === 'failed',
  ).length;

  return (
    <section className="flex flex-col gap-6">
      <header>
        <h1 className="text-2xl font-bold text-texto sm:text-3xl">
          {tituloDoResultado(job)}
        </h1>

        <p className="mt-2 text-sm text-texto-suave" aria-live="polite">
          {prontas} de {job.num_variations} variações prontas
          {comFalha > 0 ? ` · ${comFalha} não puderam ser geradas` : ''}.
        </p>
      </header>

      {job.status === 'failed' ? (
        <Alerta
          tom="erro"
          titulo={
            prontas === 0
              ? 'Nenhuma variação foi gerada'
              : 'A geração terminou com falha'
          }
          mensagem={
            prontas === 0
              ? `${motivoDaFalhaDoJob(job)} Tente enviar outro arquivo ou ` +
                'reduzir o número de variações.'
              : `${motivoDaFalhaDoJob(job)} As variações que ficaram prontas ` +
                'continuam disponíveis abaixo.'
          }
          {...(prontas === 0
            ? {
                rotuloDaAcao: 'Enviar outro vídeo',
                aoAcionar: aoComecarDeNovo,
              }
            : {})}
        />
      ) : null}

      {job.status === 'expired' ? (
        <Alerta
          tom="aviso"
          titulo="Este trabalho expirou"
          mensagem="Os arquivos ficam disponíveis por tempo limitado. Envie o
                    vídeo novamente para gerar novas variações."
        />
      ) : null}

      {comFalha > 0 && prontas > 0 ? (
        <Alerta
          tom="aviso"
          titulo="Algumas variações não ficaram prontas"
          mensagem={`${comFalha} de ${job.num_variations} falharam. As demais
                     estão disponíveis para download abaixo.`}
        />
      ) : null}

      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <Botao
          onClick={() => downloadDoZip.mutate(job.job_id)}
          carregando={downloadDoZip.isPending}
          disabled={prontas === 0}
        >
          Baixar todas em .zip
        </Botao>

        <Botao variante="secundario" onClick={aoComecarDeNovo}>
          Enviar outro vídeo
        </Botao>
      </div>

      {downloadDoZip.isError ? (
        <Alerta
          tom="erro"
          titulo="Não deu para baixar o pacote"
          mensagem={mensagemDeErro(downloadDoZip.error)}
        />
      ) : null}

      <PainelDeVariacoes
        jobId={job.job_id}
        statusDoJob={job.status}
        variacoes={job.variations}
        mensagemVazia="Nenhuma variação foi criada para este vídeo."
      />
    </section>
  );
}

function tituloDoResultado(job: Job): string {
  if (job.status === 'completed') {
    return 'Suas variações estão prontas';
  }

  if (job.status === 'cancelled') {
    return 'Geração cancelada';
  }

  return rotuloDoStatusDoJob(job.status);
}
