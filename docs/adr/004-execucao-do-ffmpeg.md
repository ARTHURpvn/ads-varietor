# ADR-004: `asyncio.create_subprocess_exec` com semáforo, worker único

**Status:** Aceito
**Data:** 2026-07-21
**Decisores:** dono do projeto

## Contexto

O trabalho pesado acontece dentro do FFmpeg, num processo separado. O processo
Python não faz trabalho de CPU: ele espera por processos filhos. Além disso, o
`DELETE /jobs/{id}` precisa realmente interromper o processamento — não basta
marcar o job como cancelado enquanto o FFmpeg continua queimando CPU.

## Decisão

Cada variação é um `asyncio.create_subprocess_exec`, limitado por um
`asyncio.Semaphore(MAX_CONCURRENT_FFMPEG)`. O job inteiro é uma `asyncio.Task`
registrada no `JobRunner`, o que permite cancelá-la. Uvicorn roda com um único
worker.

O cancelamento propaga: `task.cancel()` levanta `CancelledError` dentro de
`render_variation`, que chama `process.terminate()` antes de repassar a
exceção.

## Alternativas avaliadas

| Alternativa | Prós | Contras | Descartada porque |
|---|---|---|---|
| **asyncio subprocess + semáforo** | Não bloqueia o event loop; cancelamento nativo; GIL irrelevante | Exige `await` em todo o caminho; a CLI precisa de `asyncio.run` | — (escolhida) |
| `ThreadPoolExecutor` + `subprocess.run` | Já existia no código original | Cancelar um `Future` em execução não mata o FFmpeg; threads ficam ociosas só esperando | Não atende ao cancelamento |
| `BackgroundTasks` do FastAPI | Menos código | Sem limite de concorrência, sem cancelamento, sem visibilidade | Um POST com N alto derruba a máquina |
| Celery + Redis | Escala horizontal e retry | Broker, worker e supervisão para um único servidor | Fila externa descartada no escopo |

## Consequências

### Positivas
- `DELETE` realmente para o processamento.
- A concorrência é explícita e configurável, sem saturar a CPU.

### Negativas / Débitos técnicos
- [DÉBITO] O estado de execução vive no processo. Escalar para vários workers
  ou várias máquinas exigirá um broker externo. Impacto: Alto se houver
  crescimento · Urgência: backlog · Dono: mantenedor. Mitigação atual: o SQLite
  é a fonte de verdade e os jobs interrompidos por restart são marcados como
  falha na subida.

## Conformidade

O comando do FFmpeg é sempre uma lista de argumentos, executada sem shell.
Nenhum dado do usuário pode ser interpolado numa string de comando.
