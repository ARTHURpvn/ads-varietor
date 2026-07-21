# ADS Varietor

Gera várias cópias de um vídeo em que **cada arquivo é diferente do original** —
hash distinto, metadados distintos — para que a mesma peça possa ser publicada
mais de uma vez sem ser tratada como arquivo repetido.

Dois modos, com custos bem diferentes:

| Modo | O que faz | Tempo |
|---|---|---|
| **Variações** | Reencoda aplicando zoom, cor, velocidade e ruído. A imagem muda. | minutos |
| **Identidade** | Copia os streams sem reencodar. Imagem e som idênticos; muda só a identificação interna. | menos de 1s |

Interface web, API HTTP e linha de comando, sobre o mesmo motor.

---

## Como funciona

Cada cópia recebe um conjunto próprio de alterações:

- **Enquadramento** — zoom de 1,02x a 1,08x com corte centralizado. A resolução
  do original é preservada e não sobra faixa de fundo.
- **Cor** — brilho, contraste, saturação ou matiz, mais um véu de cor de 2% a
  6%. Forte o bastante para mudar os pixels, fraco o bastante para não lavar a
  imagem (PSNR de 30 a 40 dB contra o original).
- **Velocidade** — entre 1,000x e 1,050x, com casas decimais não redondas.
- **Áudio** — ruído em torno de -75 dB, contra -21 dB de um áudio comum. O
  volume do original não é alterado.
- **Metadados** — título, autor, gênero e data sorteados, mais um identificador
  único por arquivo. A assinatura `encoder=Lavf...` do FFmpeg é removida.

O MD5 do arquivo de origem e o de cada saída são calculados e devolvidos pela
API, para conferir que nenhum se repete.

## Requisitos

- Python 3.11+
- Node 20+ (para a interface)
- FFmpeg e ffprobe no PATH (`brew install ffmpeg` ou `apt install ffmpeg`)

## Rodando local

```bash
make setup      # venv, dependências e um .env com API key gerada
make api        # API em http://127.0.0.1:8037
make frontend   # interface em http://127.0.0.1:5173
```

O `make setup` gera uma API key automaticamente. O serviço **se recusa a
iniciar** com chave de exemplo ou com menos de 24 caracteres.

### Linha de comando

```bash
make run VIDEO=entrada.mp4 N=10
```

## API

Base: `/api/v1`. Autenticação por header `X-API-Key`.

| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/jobs` | Cria o job. Campos: `file`, `num_variations`, `mode` |
| `GET` | `/jobs/{id}` | Estado, progresso e hash de cada saída |
| `GET` | `/jobs/{id}/variations/{vid}/download` | Baixa uma variação |
| `GET` | `/jobs/{id}/download` | Baixa todas em ZIP |
| `DELETE` | `/jobs/{id}` | Cancela um job em andamento |
| `GET` | `/usage` | Uso de disco, quotas e jobs por estado |
| `GET` | `/health` | Estado do serviço |

O processamento é assíncrono: o `POST` responde `202` com um `job_id` e o
cliente acompanha por polling. Erros seguem
[RFC 9457](https://www.rfc-editor.org/rfc/rfc9457) (`application/problem+json`).

Documentação interativa em `/docs` com o serviço no ar.

## Deploy

```bash
cp .env.example .env    # preencha API_KEYS e API_KEY_FRONTEND
make docker-up
```

Sobe dois serviços: `api` (privado, só na rede interna) e `web`, um Caddy que
serve a interface na porta **8037** e **injeta a API key** nas chamadas
`/api/*` — a chave nunca chega ao navegador. O frontend é buildado dentro da
imagem, então o deploy não depende de nada compilado na sua máquina.

TLS fica com o proxy da plataforma. O compose está pronto para **Coolify**:
sem portas publicadas, sem rede declarada e com `SERVICE_FQDN_WEB_8037` para o
domínio. Passo a passo, backup e limpeza em
[docs/OPERACAO.md](docs/OPERACAO.md).

## Segurança

O serviço aceita upload e executa FFmpeg, então a superfície é tratada em
camadas:

- Chaves guardadas como SHA-256, comparadas em tempo constante
- Rate limit por chave, para requisições e para criação de jobs
- Limite de upload aplicado durante a gravação, em blocos
- Validação por `ffprobe` — extensão e `Content-Type` não são aceitos como prova
- Nome do arquivo enviado é descartado; o upload vira um UUID
- Caminhos resolvidos e conferidos contra o diretório base (`..`, absoluto e
  symlink são bloqueados)
- Quota de disco global e por chave; retenção com limpeza automática
- Comando do FFmpeg montado como lista, sem shell

## Desenvolvimento

```bash
.venv/bin/pytest              # 367 testes
cd frontend && npx vitest run # 219 testes
```

Decisões de arquitetura e seus trade-offs estão em [docs/adr/](docs/adr/).

## Limitações conhecidas

- A quota por chave **não isola usuários da interface web**: o proxy injeta uma
  única chave para todo o tráfego do navegador. Ela separa apenas clientes que
  chamam a API diretamente com chaves próprias.
- Um worker por processo. O estado de execução vive em memória; escalar
  horizontalmente exigiria um broker externo.
- `make` e os scripts foram exercitados em macOS e Linux.

## Licença

MIT.
