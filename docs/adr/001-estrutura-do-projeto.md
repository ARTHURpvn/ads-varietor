# ADR-001: Layout `src/` com pacote único

**Status:** Aceito
**Data:** 2026-07-21
**Decisores:** dono do projeto

## Contexto

O projeto era quatro scripts Python soltos na raiz, com import direto entre
eles (`from video_variations_system import ...`), seis markdowns duplicando
informação e nenhum arquivo de packaging. Para a API importar o motor sem
arrastar a CLI junto, o código precisava virar um pacote instalável.

## Decisão

Adotamos o layout `src/` com um pacote único, `video_variations`, dividido em
três camadas: `core/` (motor, sem nenhum conhecimento de HTTP), `api/`
(FastAPI) e `cli/` (argparse). O frontend fica em `frontend/`, na raiz.

## Alternativas avaliadas

| Alternativa | Prós | Contras | Descartada porque |
|---|---|---|---|
| **Layout `src/`** | Impossível importar o código não instalado por acidente; testes rodam contra o pacote real | Um nível de diretório a mais | — (escolhida) |
| Flat, pacote na raiz | Menos indireção | `import` acha o diretório local mesmo sem instalar: o teste passa e o deploy quebra | Mascara erro de packaging |
| Dois pacotes (core + api) | Isolamento forte entre motor e serviço | Dois `pyproject.toml`, instalação dupla, nenhum ganho num projeto de um mantenedor | Complexidade sem retorno |

## Consequências

### Positivas
- `pip install -e .` e `import video_variations` funcionam de forma previsível.
- A separação `core`/`api` mantém o motor reutilizável pela CLI e por testes.

### Negativas / Débitos técnicos
- Nenhum débito relevante gerado por esta decisão.

## Conformidade

`pip install -e .` seguido de `python -c "import video_variations"` faz parte
da verificação. `core/` não pode importar `fastapi` — uma violação disso
significa que a camada vazou.
