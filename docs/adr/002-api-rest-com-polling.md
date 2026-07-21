# ADR-002: REST com polling, versionado em `/api/v1`

**Status:** Aceito
**Data:** 2026-07-21
**Decisores:** dono do projeto

## Contexto

Gerar variações é demorado — cada variação é uma invocação de FFmpeg. Uma
requisição síncrona ficaria pendurada por minutos e morreria em qualquer
timeout de proxy. O cliente precisa acompanhar o andamento.

## Decisão

Comandos são REST síncronos; o processamento é um job assíncrono acompanhado
por polling.

| Método | Rota | Retorno |
|---|---|---|
| `POST` | `/api/v1/jobs` | `202` com `job_id` |
| `GET` | `/api/v1/jobs/{id}` | estado e progresso |
| `GET` | `/api/v1/jobs/{id}/variations/{vid}/download` | `video/mp4` |
| `GET` | `/api/v1/jobs/{id}/download` | `application/zip` |
| `DELETE` | `/api/v1/jobs/{id}` | `204`, cancela |
| `GET` | `/api/v1/health` | estado do serviço |

Estados: `pending → running → completed | failed | cancelled | expired`.
Estado terminal nunca retrocede.

Erros seguem RFC 9457 (`application/problem+json`). O campo `detail` é escrito
para o usuário final e nunca contém caminho de arquivo, stack trace ou saída
crua do FFmpeg.

## Alternativas avaliadas

| Alternativa | Prós | Contras | Descartada porque |
|---|---|---|---|
| **Polling** | Funciona atrás de qualquer proxy ou CDN; sem estado de conexão; retry natural | Latência de até um intervalo; requisições ociosas | — (escolhida) |
| SSE / WebSocket | Progresso instantâneo | Conexão longa quebra em proxy e em rede móvel; exige reconexão e heartbeat; multiplica estado no servidor | Custo alto para um ganho cosmético |

O cliente usa intervalo adaptativo: 1s nos primeiros 30s, 3s depois, teto de
5s. O servidor responde o status com `Cache-Control: no-store`.

## Consequências

### Positivas
- Cliente e servidor ficam desacoplados; uma queda de rede não perde o job.

### Negativas / Débitos técnicos
- [DÉBITO] O progresso tem granularidade de variação inteira, não de percentual
  dentro de uma variação. Impacto: Baixo · Urgência: backlog · Dono: mantenedor.
