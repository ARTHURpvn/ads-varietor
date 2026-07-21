import { Component, type ErrorInfo, type ReactNode } from 'react';
import { Alerta } from './Alerta.tsx';

interface LimiteDeErroProps {
  children: ReactNode;
}

interface LimiteDeErroState {
  falhou: boolean;
}

/** Garante que uma falha inesperada nunca resulte em tela em branco. */
export class LimiteDeErro extends Component<
  LimiteDeErroProps,
  LimiteDeErroState
> {
  override state: LimiteDeErroState = { falhou: false };

  static getDerivedStateFromError(): LimiteDeErroState {
    return { falhou: true };
  }

  override componentDidCatch(erro: Error, info: ErrorInfo): void {
    // Log técnico fica no console; a UI mostra só linguagem de usuário.
    console.error('Falha inesperada na interface', erro, info);
  }

  override render(): ReactNode {
    if (this.state.falhou) {
      return (
        <div className="p-4">
          <Alerta
            tom="erro"
            titulo="Algo deu errado por aqui"
            mensagem="A página encontrou um problema inesperado. Recarregue
                      para continuar de onde parou."
            rotuloDaAcao="Recarregar página"
            aoAcionar={() => window.location.reload()}
          />
        </div>
      );
    }

    return this.props.children;
  }
}
