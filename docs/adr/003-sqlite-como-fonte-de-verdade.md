# ADR-003: SQLite (WAL) como fonte de verdade dos jobs

**Status:** Aceito
**Data:** 2026-07-21
**Decisores:** dono do projeto

## Contexto

O estado de um job precisa sobreviver a um restart do serviço: quem enviou um
vídeo e fechou a aba tem que reencontrar o resultado. O volume esperado é de
dezenas de jobs por dia, num único processo servidor.

## Decisão

SQLite com `journal_mode=WAL`, acessado pelo módulo `sqlite3` da biblioteca
padrão atrás de um `JobRepository`. Três tabelas: `jobs`, `variations` e
`rate_limit_events`, mais `schema_version`. Todo SQL usa placeholders `?`.

Índices: `jobs(api_key_hash)` para o isolamento entre chaves,
`jobs(status, created_at)` para a rotina de retenção, e
`rate_limit_events(api_key_hash, event_type, created_at)` para o rate limit.

## Alternativas avaliadas

| Alternativa | Prós | Contras | Descartada porque |
|---|---|---|---|
| **SQLite + `sqlite3` stdlib** | Zero dependência; ACID; sobrevive a restart; suporta índice e consulta de limpeza | Sem migrations prontas; escrita serializada | — (escolhida) |
| Dicionário em memória | Mais simples | Perde tudo no restart | Requisito explícito de persistência |
| Um JSON por job em disco | Sem SQL | Listar e limpar vira varredura de diretório; escrita concorrente sem lock corrompe | Race condition real |
| SQLAlchemy + Alembic | Migrations e ORM | Dependência pesada e uma camada de abstração para duas tabelas | Desproporcional ao tamanho |

## Consequências

### Positivas
- Um restart não perde nada; jobs presos em `running` são marcados como falha
  na subida, o que evita job fantasma.
- O rate limit compartilha o mesmo armazenamento, sem outro serviço.

### Negativas / Débitos técnicos
- [DÉBITO] Sem ferramenta de migration: mudar o schema exigirá script manual.
  Impacto: Médio · Urgência: backlog · Dono: mantenedor. Mitigado em parte pela
  tabela `schema_version`, presente desde a v1.

## Conformidade

Nenhuma query pode ser montada com f-string ou concatenação; toda passagem de
valor usa placeholder.
