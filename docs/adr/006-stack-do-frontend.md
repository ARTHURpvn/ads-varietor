# ADR-006: React 19 + Vite + TypeScript strict

**Status:** Aceito
**Data:** 2026-07-21
**Decisores:** dono do projeto

## Contexto

O frontend tem um fluxo linear de três telas — envio, progresso, resultados — e
precisa acompanhar um job por polling. Não há autenticação de usuário, rota
profunda nem conteúdo indexável.

## Decisão

SPA em React 19 + Vite 7 + TypeScript com `strict`, `noUncheckedIndexedAccess`
e `exactOptionalPropertyTypes`. Estado de servidor com TanStack Query. Estilo
com Tailwind v4. Sem router: uma máquina de estados local cobre o fluxo.

Em desenvolvimento, o proxy do Vite repassa `/api` para a API local e injeta o
`X-API-Key` a partir de `DEV_API_KEY` — variável do processo Node, sem prefixo
`VITE_`, portanto nunca embutida no bundle. É o mesmo papel que o reverse proxy
faz em produção.

## Alternativas avaliadas

| Camada | Escolhido | Alternativa descartada | Motivo |
|---|---|---|---|
| Build | Vite | Next.js | SSR e rotas de servidor sem uso; deploy mais pesado |
| Estado de servidor | TanStack Query | `useEffect` + `setInterval` | Reimplementa retry, cancelamento e deduplicação; fonte comum de vazamento de timer |
| Estilo | Tailwind v4 | CSS Modules | Viável, mas mais arquivos e menos consistência de espaçamento |
| Rotas | Máquina de estados local | react-router | Três telas de um fluxo linear não justificam |

## Consequências

### Positivas
- O polling adaptativo e o cancelamento vêm prontos da biblioteca de query.
- Nenhum segredo chega ao bundle.

### Negativas / Débitos técnicos
- [DÉBITO] Sem router, recarregar a página perde o contexto de navegação. Já
  mitigado guardando o `job_id` no `localStorage` e oferecendo retomada.
  Impacto: Baixo · Urgência: backlog · Dono: mantenedor.

## Conformidade

`npx tsc --noEmit` sem erros e `npm run build` limpo. Nenhum `any` sem
justificativa em comentário.
