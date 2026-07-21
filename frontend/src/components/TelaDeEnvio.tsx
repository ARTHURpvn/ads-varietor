import { useId, useState, type FormEvent, type ReactElement } from 'react';
import { useSaudeDoServico } from '../hooks/useSaudeDoServico.ts';
import { AreaDeUpload } from './AreaDeUpload.tsx';
import { Alerta } from './Alerta.tsx';
import { Botao } from './Botao.tsx';

export const MINIMO_DE_VARIACOES = 1;
export const MAXIMO_DE_VARIACOES = 50;
const PADRAO_DE_VARIACOES = 5;

interface TelaDeEnvioProps {
  enviando: boolean;
  /** Erro vindo da API já traduzido, ou null. */
  erroDoEnvio: string | null;
  /** Descarta o erro da tentativa anterior de envio. */
  aoLimparErroDoEnvio: () => void;
  aoEnviar: (arquivo: File, numeroDeVariacoes: number) => void;
  /** Oferta de retomar um trabalho salvo anteriormente. */
  jobSalvo?: { jobId: string; aoRetomar: () => void; aoDescartar: () => void };
}

export function TelaDeEnvio({
  enviando,
  erroDoEnvio,
  aoLimparErroDoEnvio,
  aoEnviar,
  jobSalvo,
}: TelaDeEnvioProps): ReactElement {
  const campoQuantidadeId = useId();
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [quantidade, setQuantidade] = useState<number>(PADRAO_DE_VARIACOES);
  const [erroLocal, setErroLocal] = useState<string | null>(null);
  const saude = useSaudeDoServico();
  const servicoDegradado = saude.data?.status === 'degraded';

  /** Toda troca de arquivo zera o erro local E o da última tentativa. */
  function limparErros(): void {
    setErroLocal(null);
    aoLimparErroDoEnvio();
  }

  function aoSubmeter(evento: FormEvent<HTMLFormElement>): void {
    evento.preventDefault();

    if (arquivo === null) {
      setErroLocal('Escolha um vídeo antes de gerar as variações.');
      return;
    }

    if (
      !Number.isInteger(quantidade) ||
      quantidade < MINIMO_DE_VARIACOES ||
      quantidade > MAXIMO_DE_VARIACOES
    ) {
      setErroLocal(
        `Escolha um número de variações entre ${MINIMO_DE_VARIACOES} e ` +
          `${MAXIMO_DE_VARIACOES}.`,
      );
      return;
    }

    setErroLocal(null);
    aoEnviar(arquivo, quantidade);
  }

  const mensagemDeErro = erroLocal ?? erroDoEnvio;

  return (
    <section className="flex flex-col gap-6">
      <header>
        <h1 className="text-2xl font-bold text-texto sm:text-3xl">
          Gere variações do seu vídeo
        </h1>
        <p className="mt-2 text-sm text-texto-suave sm:text-base">
          Envie um vídeo e escolha quantas versões você quer. Cada versão sai
          com velocidade, cor e escala levemente diferentes.
        </p>
      </header>

      {servicoDegradado ? (
        <Alerta
          tom="aviso"
          titulo="O serviço está instável agora"
          mensagem="O processador de vídeo está indisponível no servidor. Você
                    pode enviar mesmo assim, mas a geração provavelmente vai
                    falhar. Se puder, tente de novo em alguns minutos."
        />
      ) : null}

      {jobSalvo !== undefined ? (
        <Alerta
          tom="informacao"
          titulo="Você tem um trabalho em andamento"
          mensagem="Podemos abrir o acompanhamento do último vídeo enviado."
          rotuloDaAcao="Retomar"
          aoAcionar={jobSalvo.aoRetomar}
        />
      ) : null}

      <form onSubmit={aoSubmeter} className="flex flex-col gap-5">
        <AreaDeUpload
          arquivoSelecionado={arquivo}
          desabilitado={enviando}
          aoSelecionar={(selecionado) => {
            limparErros();
            setArquivo(selecionado);
          }}
          aoRejeitar={(mensagem) => {
            limparErros();
            setArquivo(null);
            setErroLocal(mensagem);
          }}
        />

        <div className="flex flex-col gap-2">
          <label
            htmlFor={campoQuantidadeId}
            className="text-sm font-semibold text-texto"
          >
            Quantas variações você quer?
          </label>

          <input
            id={campoQuantidadeId}
            type="number"
            inputMode="numeric"
            min={MINIMO_DE_VARIACOES}
            max={MAXIMO_DE_VARIACOES}
            step={1}
            value={quantidade}
            disabled={enviando}
            onChange={(evento) => {
              const valor = Number.parseInt(evento.target.value, 10);
              setQuantidade(Number.isNaN(valor) ? MINIMO_DE_VARIACOES : valor);
            }}
            className="w-full max-w-40 rounded-lg border border-borda
                       bg-superficie px-3 py-2.5 text-base text-texto"
          />

          <p className="text-xs text-texto-suave">
            De {MINIMO_DE_VARIACOES} até {MAXIMO_DE_VARIACOES} variações por
            envio.
          </p>
        </div>

        {mensagemDeErro !== null ? (
          <Alerta
            tom="erro"
            titulo="Não deu para começar"
            mensagem={mensagemDeErro}
          />
        ) : null}

        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <Botao type="submit" carregando={enviando} className="sm:w-auto">
            {enviando ? 'Enviando vídeo...' : 'Gerar variações'}
          </Botao>

          {jobSalvo !== undefined ? (
            <Botao variante="secundario" onClick={jobSalvo.aoDescartar}>
              Descartar trabalho anterior
            </Botao>
          ) : null}
        </div>
      </form>
    </section>
  );
}
