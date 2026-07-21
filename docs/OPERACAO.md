# Operação e deploy

Guia de quem mantém o serviço no ar. Cobre deploy com Docker, ciclo de vida
dos arquivos, quotas e como não deixar o disco encher.

---

## 1. Por que o disco enche

Um job de 50 variações de um vídeo de 100 MB grava cerca de 5 GB: a entrada
uma vez e a saída cinquenta. Sem retenção agressiva, alguns dias de uso
normal consomem dezenas de GB.

Três mecanismos independentes seguram isso:

| Mecanismo | O que faz | Configuração |
|---|---|---|
| Ciclo de vida da entrada | Apaga o vídeo enviado assim que o job termina, em qualquer desfecho | automático |
| Retenção | Apaga jobs terminados por idade | `RETENTION_HOURS` |
| Reconciliação | Remove lixo que sobrou de um crash | `RECONCILE_ENABLED` |

E dois limites que recusam trabalho antes de gravar:
`MAX_STORAGE_BYTES` (serviço) e `MAX_STORAGE_BYTES_PER_KEY` (por chave).

---

## 2. Ciclo de vida de um arquivo

```
upload  ──▶  jobs/<job_id>/*.mp4  ──▶  download  ──▶  apagado
   │                                                     ▲
   └── apagado quando o job termina ─────────────────────┘
        (concluído, falho OU cancelado)
```

- **Entrada**: apagada no `finally` do runner. Vale para sucesso, falha e
  cancelamento. Um cancelamento de job ainda pendente (sem task viva)
  apaga o upload na própria rota `DELETE`.
- **Saída**: apagada pela retenção, ou logo depois do ZIP quando
  `DELETE_AFTER_BATCH_DOWNLOAD=true`.
- **Órfãos**: uploads que nunca viraram job são apagados pela
  reconciliação, respeitando `UNREFERENCED_UPLOAD_GRACE_SECONDS`.

### Retenção: por que 6 horas e não 24

O padrão anterior era 24 h. O fluxo real do produto é criar o job e baixar
em minutos — não no dia seguinte. Segurar vários GB por um dia inteiro só
para o caso raro de alguém voltar amanhã custa caro em disco e é a causa
mais comum de serviço parado por `507`. Suba para 24 apenas se os seus
usuários de fato rebaixam no dia seguinte.

### `DELETE_AFTER_BATCH_DOWNLOAD` — o trade-off

**Ligado**: os arquivos do job somem assim que o ZIP termina de ser enviado
e o job vira `expired`. Libera vários GB por job, na hora.

**Custo**: não existe segunda chance. Um download interrompido no meio
(queda de rede, usuário fechou a aba) leva os arquivos junto — o cliente
precisa refazer o job inteiro, gastando CPU de novo. Também quebra o
download individual por variação depois do lote.

**Recomendação**: deixe desligado (default) e resolva pelo `RETENTION_HOURS`.
Ligue apenas quando o disco for comprovadamente o gargalo e os jobs forem
grandes o bastante para justificar o risco de refazer.

### Reconciliação

Um crash entre "apagar os arquivos" e "marcar como expirado" deixava lixo
que nenhuma rotina voltava a olhar. A reconciliação roda no start e a cada
ciclo de limpeza:

- diretório em `jobs/` sem registro correspondente → **apagado**;
- job `completed` cujo diretório sumiu → **marcado como expirado**;
- upload que nenhum job ativo reivindica e passou da folga → **apagado**.

---

## 3. Quotas

| Limite | Escopo | Resposta ao estourar |
|---|---|---|
| `MAX_STORAGE_BYTES` | serviço inteiro | `507` — *"Sem espaço disponível"* |
| `MAX_STORAGE_BYTES_PER_KEY` | por chave de API | `507` — *"Seu limite de armazenamento foi atingido"* |

As duas causas de `507` têm `title` diferente justamente para o cliente
saber se o problema é dele ou do serviço. A mensagem do limite individual
cita apenas a quota da própria chave: nem o total global nem o consumo de
outras chaves aparecem.

A quota global é checada antes do upload, pelo pior caso
(`MAX_UPLOAD_BYTES × (1 + variações)`). A quota por chave é checada depois,
com o tamanho real do arquivo recebido — o que evita recusar job legítimo
por uma estimativa pessimista.

---

## 4. Visibilidade

### `GET /api/v1/usage`

Autenticado. Devolve:

```json
{
  "used_bytes": 3221225472,
  "quota_bytes": 21474836480,
  "available_bytes": 18253611008,
  "usage_percent": 15.0,
  "warn_percent": 80,
  "over_threshold": false,
  "retention_hours": 6,
  "jobs_by_status": { "completed": 12, "failed": 1 },
  "your_usage": {
    "jobs": 4,
    "jobs_by_status": { "completed": 4 },
    "used_bytes": 1073741824,
    "quota_bytes": 10737418240,
    "available_bytes": 9663676416,
    "usage_percent": 10.0
  }
}
```

O total global vem do disco de verdade; o total por chave vem do banco,
porque o filesystem não sabe de quem é cada byte.

### Log estruturado

Uma linha JSON por evento em stdout (`LOG_JSON=true`). Eventos:

| `event` | Quando | Campos |
|---|---|---|
| `job.created` | job aceito | `job_id`, `owner`, `bytes`, `num_variations`, `mode` |
| `job.completed` | todas/algumas variações prontas | `job_id`, `owner`, `duration_seconds`, `bytes` |
| `job.failed` | nenhuma variação gerada | `job_id`, `owner`, `duration_seconds` |
| `job.cancelled` | cancelado pelo cliente ou shutdown | `job_id`, `owner`, `duration_seconds` |
| `job.purged_after_download` | purga pós-ZIP | `job_id`, `owner`, `bytes` |
| `cleanup.retention` | limpeza por idade | `jobs_removed`, `duration_seconds` |
| `cleanup.reconcile` | reconciliação corrigiu algo | `orphan_directories`, `missing_directories`, `orphan_uploads` |
| `quota.key_exceeded` | chave estourou a própria quota | `owner`, `bytes`, `quota_bytes` |
| `storage.threshold_exceeded` | uso passou de `STORAGE_WARN_PERCENT` | `bytes`, `usage_percent`, `threshold_percent` |

**O que nunca aparece no log**: a API key (só um prefixo de 12 hex do hash
dela, no campo `owner`) e o nome do arquivo enviado pelo usuário.

Alerta mínimo recomendado: qualquer linha com
`event = storage.threshold_exceeded`.

---

## 5. Deploy com Docker

```bash
cp .env.example .env         # preencha API_KEYS
make docker-up               # sobe em http://127.0.0.1:8037
```

Um container só: a mesma aplicação serve a interface e a API na porta 8037.
O frontend é buildado dentro da imagem (estágio Node no `Dockerfile`), então
o deploy não depende de `frontend/dist` existir na máquina — o que importa,
já que `dist/` é ignorado pelo git.

```
internet ──443──▶ proxy da plataforma ──8037──▶ app
                  (Traefik do Coolify)          ├── interface (estáticos)
                                                └── API (/api/v1/*)
```

### Acesso

| Origem | Como autentica |
|---|---|
| Interface web | Sem chave, quando `UI_PUBLIC=true`. Dono público compartilhado, com quota e rate limit próprios. |
| Uso programático | `X-API-Key` obrigatória. Quota e rate limit por chave. |

`UI_PUBLIC=true` deixa a API acessível a qualquer visitante do endereço — o
mesmo alcance que um proxy injetando uma chave única para todos teria, só que
declarado. Com `false`, toda chamada exige chave e a interface não funciona
sozinha.

Jobs criados pela interface pública não são visíveis para quem usa chave, e
vice-versa.

### Deploy no Coolify

O compose já está no formato esperado:

- **Sem portas publicadas** — publicar contornaria o proxy.
- **Sem rede declarada** — o Coolify cria uma por stack.
- **Sem TLS na aplicação** — o Traefik do Coolify termina HTTPS.
- **`SERVICE_FQDN_APP_8037`** aponta o domínio para a porta 8037.

Crie um recurso *Docker Compose* apontando para o repositório, defina
`API_KEYS`, decida o `UI_PUBLIC`, atribua o domínio e faça o deploy. O volume
`storage` é nomeado e sobrevive a redeploys.

### Fora do Coolify

`make docker-up` gera um override que publica a 8037 no host. Ponha um proxy
com TLS na frente antes de expor à internet.

## 6. Backup e limpeza do volume

O storage vive num volume nomeado (`<projeto>_storage`), que sobrevive a
`docker compose down` e a troca de imagem.

```bash
make storage-usage      # quanto está ocupado
make storage-backup     # gera storage-backup-AAAAMMDD-HHMMSS.tar.gz
```

O backup roda num container efêmero montando o volume como somente-leitura,
então não exige a API de pé. Restaurar:

```bash
docker run --rm \
  -v <projeto>_storage:/data \
  -v "$PWD":/backup \
  alpine tar xzf /backup/storage-backup-AAAAMMDD-HHMMSS.tar.gz -C /data
```

Vale a pena fazer backup? Em geral **não** dos vídeos: eles são derivados e
descartáveis por definição. O que interessa é `jobs.sqlite3`, e só se você
quiser preservar histórico — os arquivos correspondentes provavelmente já
expiraram.

Limpeza total (destrutiva, pede confirmação):

```bash
make storage-purge
```

Para liberar espaço sem apagar tudo, prefira baixar `RETENTION_HOURS` e
esperar o próximo ciclo de limpeza: é reversível e não derruba o serviço.
