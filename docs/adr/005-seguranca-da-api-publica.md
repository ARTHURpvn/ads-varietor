# ADR-005: API key com hash, rate limit em SQLite, TLS no proxy

**Status:** Aceito
**Data:** 2026-07-21
**Decisores:** dono do projeto

## Contexto

A API fica exposta na internet, aceita upload de arquivo e executa um
subprocess por variação. É a maior superfície de risco do sistema: um endpoint
aberto aqui não vaza dado, ele vira capacidade de computação de graça para
terceiros — ou pior, um vetor para o parser do FFmpeg.

## Decisão

Defesa em camadas:

1. **Autenticação** — header `X-API-Key`. As chaves vêm da variável `API_KEYS`
   e são guardadas como SHA-256; a comparação usa `hmac.compare_digest`, para
   que o tempo de resposta não revele quantos caracteres estavam certos.
2. **Autorização** — o job pertence ao hash da chave que o criou. Requisição de
   outra chave recebe `404`, não `403`: responder `403` confirmaria que aquele
   job existe.
3. **Rate limit** — janela deslizante por chave, contada em SQLite. Dois
   limites: requisições por minuto e criação de jobs por hora, este bem mais
   restrito por ser a operação cara.
4. **Upload** — o limite de bytes é aplicado durante a gravação em disco, em
   blocos, abortando ao estourar. Carregar o arquivo inteiro em memória
   permitiria derrubar o serviço com um upload grande.
5. **Validação de conteúdo** — extensão e `Content-Type` não provam nada. A
   única prova aceita é o `ffprobe` confirmar que existe stream de vídeo.
6. **Nome de arquivo** — descartado. O upload vira `{uuid4}{extensão}`, com a
   extensão vinda de uma allowlist. O nome enviado nunca toca o filesystem nem
   o comando.
7. **Path traversal** — o caminho final é resolvido e conferido contra o
   diretório base; `..`, caminho absoluto e symlink são pegos depois de
   resolver, não por inspeção do texto.
8. **Quota e retenção** — espaço ocupado é checado antes de aceitar um job
   (`507` se estourar) e uma rotina periódica apaga jobs além do período de
   retenção.
9. **CORS** — allowlist explícita por variável de ambiente; nunca `*`.
10. **TLS** — terminado no reverse proxy. O uvicorn escuta apenas em
    `127.0.0.1`.

O frontend é estático: qualquer chave que ele carregasse seria pública. O
reverse proxy injeta o `X-API-Key`, e o browser nunca a vê.

## Alternativas avaliadas

| Alternativa | Prós | Contras | Descartada porque |
|---|---|---|---|
| **API key com hash** | Adequada a serviço sem contas; revogação por variável de ambiente | Chave estática, sem expiração | — (escolhida) |
| JWT | Expiração e claims | Exige emissor e refresh; não existem usuários no sistema | Complexidade sem ganho |
| `slowapi` para rate limit | Pronto para usar | Padrão em memória, perde no restart; traz dependência; a contagem por chave já ia existir | Feito em SQLite junto da quota |
| Sem auth, só rate limit por IP | Zero fricção | IP rotativo derruba a proteção | Inaceitável para processamento pesado exposto |

## Consequências

### Positivas
- Nenhum ponto único de falha: burlar uma camada ainda esbarra na seguinte.

### Negativas / Débitos técnicos
- [DÉBITO] Chave sem expiração nem rotação automática. Impacto: Médio ·
  Urgência: próximo trimestre · Dono: mantenedor.
- [DÉBITO] O serviço depende do proxy estar corretamente configurado. Um deploy
  que exponha a porta 8037 diretamente perde a camada de TLS. Documentado na
  instalação. Impacto: Alto · Urgência: sprint atual · Dono: quem opera.

## Conformidade

Cada item acima tem verificação correspondente na suíte de testes e é alvo
explícito do pentest.
