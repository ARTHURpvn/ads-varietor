import type { ReactElement, ReactNode } from 'react';
import type { Job } from '../api/types.ts';
import { useDownloadDoZip } from '../hooks/useDownloads.ts';
import { mensagemDeErro } from '../lib/erro.ts';
import { normalizarHash } from '../lib/hash.ts';
import { motivoDaFalhaDoJob, rotuloDoStatusDoJob } from '../lib/mensagens.ts';
import { descricaoDoModo, rotuloDasSaidas } from '../lib/modos.ts';
import { Alerta } from './Alerta.tsx';
import { Botao } from './Botao.tsx';
import { Icone } from './Icone.tsx';
import { IdentificacaoDoArquivo } from './IdentificacaoDoArquivo.tsx';
import { PainelDeVariacoes } from './PainelDeVariacoes.tsx';
import { TiraDeVariacoes } from './TiraDeVariacoes.tsx';
import { VerificacaoDeHashes } from './VerificacaoDeHashes.tsx';

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

  const saidas = rotuloDasSaidas(job.mode);
  const hashDeOrigem = normalizarHash(job.source_md5);

  return (
    <section className="flex flex-col gap-5 animate-surgir">
      <div
        className="flex flex-col gap-4 rounded-2xl border border-borda
                   bg-superficie p-4 shadow-[var(--sombra-cartao)] sm:p-5"
      >
        <div
          className="flex flex-wrap items-start justify-between gap-x-6
                     gap-y-4"
        >
          <header className="min-w-0">
            <p className="font-mono text-selo uppercase text-destaque">
              03 · Resultado
            </p>

            <h1
              className="mt-1.5 font-mono text-titulo font-semibold text-texto
                         sm:text-secao"
            >
              {tituloDoResultado(job)}
            </h1>

            <p className="mt-1.5 text-nota text-texto-suave" aria-live="polite">
              {prontas} de {job.num_variations} {saidas} prontas
              {comFalha > 0 ? ` · ${comFalha} não puderam ser geradas` : ''}.
            </p>
          </header>

          <div
            className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row
                       sm:items-center"
          >
            <Botao
              onClick={() => downloadDoZip.mutate(job.job_id)}
              carregando={downloadDoZip.isPending}
              disabled={prontas === 0}
              icone={<Icone nome="pacote" tamanho={15} />}
            >
              Baixar todas em .zip
            </Botao>

            <Botao variante="secundario" onClick={aoComecarDeNovo}>
              Enviar outro vídeo
            </Botao>
          </div>
        </div>

        <div
          className="grid grid-cols-2 gap-px overflow-hidden rounded-xl
                     border border-borda bg-borda sm:grid-cols-4"
        >
          <Leitura rotulo="Prontas" tom={prontas > 0 ? 'sucesso' : 'neutro'}>
            {prontas}
          </Leitura>

          <Leitura
            rotulo="Com falha"
            tom={comFalha > 0 ? 'erro' : 'neutro'}
          >
            {comFalha}
          </Leitura>

          <Leitura rotulo="Pedidas">{job.num_variations}</Leitura>

          <Leitura rotulo="Modo" compacta>
            {descricaoDoModo(job.mode).rapido ? 'Só identidade' : 'Variações'}
          </Leitura>
        </div>

        <TiraDeVariacoes
          variacoes={job.variations}
          statusDoJob={job.status}
        />

        {hashDeOrigem !== null ? (
          <IdentificacaoDoArquivo
            rotulo="Arquivo original"
            hash={hashDeOrigem}
          />
        ) : null}
      </div>

      <VerificacaoDeHashes
        variacoes={job.variations}
        hashDeOrigem={hashDeOrigem}
        modo={job.mode}
      />

      {job.status === 'failed' ? (
        <Alerta
          tom="erro"
          titulo={
            prontas === 0
              ? `Nenhuma das ${saidas} foi gerada`
              : 'A geração terminou com falha'
          }
          mensagem={
            prontas === 0
              ? `${motivoDaFalhaDoJob(job)} Tente enviar outro arquivo ou ` +
                `reduzir o número de ${saidas}.`
              : `${motivoDaFalhaDoJob(job)} As ${saidas} que ficaram prontas ` +
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
          titulo={`Algumas ${saidas} não ficaram prontas`}
          mensagem={`${comFalha} de ${job.num_variations} falharam. As demais
                     estão disponíveis para download abaixo.`}
        />
      ) : null}

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
        modo={job.mode}
        variacoes={job.variations}
        mensagemVazia={`Nenhuma ${rotuloDasSaidas(job.mode)} foi criada para
                        este vídeo.`}
      />
    </section>
  );
}

type TomDaLeitura = 'neutro' | 'sucesso' | 'erro';

interface LeituraProps {
  rotulo: string;
  tom?: TomDaLeitura;
  /** Para valores em texto, que não cabem no tamanho do numeral. */
  compacta?: boolean;
  children: ReactNode;
}

const COR_DA_LEITURA: Record<TomDaLeitura, string> = {
  neutro: 'text-texto',
  sucesso: 'text-sucesso',
  erro: 'text-erro',
};

/** Célula de leitura numérica — o painel de instrumentos do resultado. */
function Leitura({
  rotulo,
  tom = 'neutro',
  compacta = false,
  children,
}: LeituraProps): ReactElement {
  return (
    <div className="bg-superficie px-3 py-2.5">
      <p className="font-mono text-selo uppercase text-texto-fraco">
        {rotulo}
      </p>

      <p
        className={`mt-0.5 font-mono font-semibold
                    ${compacta ? 'text-nota' : 'text-titulo'}
                    ${COR_DA_LEITURA[tom]}`}
      >
        {children}
      </p>
    </div>
  );
}

function tituloDoResultado(job: Job): string {
  if (job.status === 'completed') {
    return `Suas ${rotuloDasSaidas(job.mode)} estão prontas`;
  }

  if (job.status === 'cancelled') {
    return 'Geração cancelada';
  }

  return rotuloDoStatusDoJob(job.status, job.mode);
}
