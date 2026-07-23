import { useId, useState, type FormEvent, type ReactElement } from 'react';
import type { SelecaoDeEfeitos } from '../api/jobs.ts';
import type { ProcessingMode } from '../api/types.ts';
import { useSaudeDoServico } from '../hooks/useSaudeDoServico.ts';
import { MODO_PADRAO, rotuloDasSaidas } from '../lib/modos.ts';
import { AreaDeUpload } from './AreaDeUpload.tsx';
import { Alerta } from './Alerta.tsx';
import { Botao } from './Botao.tsx';
import { Icone } from './Icone.tsx';
import { SeletorDeEfeitos } from './SeletorDeEfeitos.tsx';
import { SeletorDeModo } from './SeletorDeModo.tsx';

const EFEITOS_PADRAO: SelecaoDeEfeitos = {
  color: true,
  framing: true,
  speed: true,
  noise: true,
};

export const MINIMO_DE_VARIACOES = 1;
export const MAXIMO_DE_VARIACOES = 50;
const PADRAO_DE_VARIACOES = 5;

/** Quantidades mais pedidas, para não obrigar a digitar. */
const ATALHOS_DE_QUANTIDADE: readonly number[] = [3, 5, 10, 25, 50];

interface TelaDeEnvioProps {
  enviando: boolean;
  /** Erro vindo da API já traduzido, ou null. */
  erroDoEnvio: string | null;
  /** Descarta o erro da tentativa anterior de envio. */
  aoLimparErroDoEnvio: () => void;
  aoEnviar: (
    arquivo: File,
    numeroDeVariacoes: number,
    modo: ProcessingMode,
    efeitos: SelecaoDeEfeitos,
  ) => void;
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
  const [modo, setModo] = useState<ProcessingMode>(MODO_PADRAO);
  const [efeitos, setEfeitos] = useState<SelecaoDeEfeitos>(EFEITOS_PADRAO);
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
      setErroLocal(
        `Escolha um vídeo antes de gerar as ${rotuloDasSaidas(modo)}.`,
      );
      return;
    }

    if (
      !Number.isInteger(quantidade) ||
      quantidade < MINIMO_DE_VARIACOES ||
      quantidade > MAXIMO_DE_VARIACOES
    ) {
      setErroLocal(
        `Escolha um número de ${rotuloDasSaidas(modo)} entre ` +
          `${MINIMO_DE_VARIACOES} e ${MAXIMO_DE_VARIACOES}.`,
      );
      return;
    }

    const efeitosAtivos = modo === 'full' ? efeitos : EFEITOS_PADRAO;
    const nenhumEfeito =
      modo === 'full' &&
      !efeitosAtivos.color &&
      !efeitosAtivos.framing &&
      !efeitosAtivos.speed &&
      !efeitosAtivos.noise;
    if (nenhumEfeito) {
      setErroLocal(
        'Escolha ao menos um efeito, ou use o modo que só troca a ' +
          'identidade do arquivo.',
      );
      return;
    }

    setErroLocal(null);
    aoEnviar(arquivo, quantidade, modo, efeitosAtivos);
  }

  const mensagemDeErro = erroLocal ?? erroDoEnvio;

  return (
    <section className="flex flex-col gap-6 animate-surgir">
      <header>
        <p className="font-mono text-selo uppercase text-destaque">
          01 · Envio
        </p>

        <h1
          className="mt-1.5 font-mono text-secao font-semibold text-texto
                     sm:text-display"
        >
          Gere variações do seu vídeo
        </h1>

        <p className="mt-2 max-w-prose text-corpo text-texto-suave">
          Envie um vídeo e escolha quantas cópias você quer. Cada cópia sai
          como um arquivo diferente do original, para não ser tratada como
          repetida.
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

      <form
        onSubmit={aoSubmeter}
        className="flex flex-col gap-5 rounded-2xl border border-borda
                   bg-superficie p-4 shadow-[var(--sombra-cartao)] sm:p-5"
      >
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

        <hr className="border-borda" />

        <SeletorDeModo
          valor={modo}
          desabilitado={enviando}
          aoMudar={(escolhido) => {
            limparErros();
            setModo(escolhido);
          }}
        />

        {/* No modo que só troca a identidade nenhum efeito é aplicado, então
            o seletor só faz sentido no modo completo. */}
        {modo === 'full' ? (
          <>
            <hr className="border-borda" />
            <SeletorDeEfeitos
              valor={efeitos}
              desabilitado={enviando}
              aoMudar={(escolhidos) => {
                limparErros();
                setEfeitos(escolhidos);
              }}
            />
          </>
        ) : null}

        <hr className="border-borda" />

        <div className="flex flex-col gap-2">
          <label
            htmlFor={campoQuantidadeId}
            className="text-nota font-semibold text-texto"
          >
            Quantas {rotuloDasSaidas(modo)} você quer?
          </label>

          <div className="flex flex-wrap items-center gap-2">
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
                setQuantidade(
                  Number.isNaN(valor) ? MINIMO_DE_VARIACOES : valor,
                );
              }}
              className="w-20 rounded-lg border border-borda-forte
                         bg-fundo-alto px-3 py-2 text-center font-mono
                         text-guia font-semibold text-texto"
            />

            <div
              role="group"
              aria-label="Quantidades usadas com frequência"
              className="flex flex-wrap gap-1.5"
            >
              {ATALHOS_DE_QUANTIDADE.map((atalho) => (
                <button
                  key={atalho}
                  type="button"
                  disabled={enviando}
                  aria-pressed={quantidade === atalho}
                  onClick={() => setQuantidade(atalho)}
                  className={`min-h-9 min-w-9 rounded-lg border px-2
                              font-mono text-micro font-semibold
                              transition-colors disabled:opacity-45
                              ${
                                quantidade === atalho
                                  ? 'border-destaque bg-destaque-suave ' +
                                    'text-destaque'
                                  : 'border-borda bg-superficie ' +
                                    'text-texto-suave ' +
                                    'hover:border-borda-forte hover:text-texto'
                              }`}
                >
                  {atalho}
                </button>
              ))}
            </div>
          </div>

          <p className="text-micro text-texto-fraco">
            De {MINIMO_DE_VARIACOES} até {MAXIMO_DE_VARIACOES}{' '}
            {rotuloDasSaidas(modo)} por envio.
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
          <Botao
            type="submit"
            carregando={enviando}
            icone={<Icone nome="raio" tamanho={15} />}
          >
            {enviando ? 'Enviando vídeo...' : `Gerar ${rotuloDasSaidas(modo)}`}
          </Botao>

          {jobSalvo !== undefined ? (
            <Botao variante="discreto" onClick={jobSalvo.aoDescartar}>
              Descartar trabalho anterior
            </Botao>
          ) : null}
        </div>
      </form>
    </section>
  );
}
