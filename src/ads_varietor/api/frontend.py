"""Serviço dos arquivos estáticos da interface, na mesma origem da API.

Antes isto era papel de um Caddy num container separado. Trazer para cá
elimina um container e um salto de rede; em troca, os cabeçalhos de cache e
de segurança que o proxy dava de graça passam a ser responsabilidade daqui.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.staticfiles import StaticFiles

# Os arquivos gerados pelo Vite trazem hash no nome, então o conteúdo de um
# dado caminho nunca muda: podem ser guardados para sempre.
CACHE_DOS_ASSETS = "public, max-age=31536000, immutable"
# O index aponta para a versão atual dos assets; cacheá-lo serviria a
# interface velha depois de um deploy.
CACHE_DO_INDEX = "no-cache"

CABECALHOS_DE_SEGURANCA = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    # A interface e a API são a mesma origem; nada externo é carregado.
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data: blob:; "
        "media-src 'self' blob:; style-src 'self' 'unsafe-inline'; "
        "object-src 'none'; frame-ancestors 'none'; base-uri 'self'"
    ),
}


class InterfaceEstatica(StaticFiles):
    """StaticFiles com os cabeçalhos de cache corretos por tipo de arquivo."""

    def file_response(self, *args: object, **kwargs: object) -> Response:
        resposta = super().file_response(*args, **kwargs)  # type: ignore[arg-type]
        caminho = str(getattr(resposta, "path", ""))
        if "/assets/" in caminho:
            resposta.headers["Cache-Control"] = CACHE_DOS_ASSETS
        else:
            resposta.headers["Cache-Control"] = CACHE_DO_INDEX
        return resposta


def montar_interface(app: FastAPI, diretorio: Path, *, api_prefix: str) -> None:
    """Serve o build do frontend em todas as rotas fora do prefixo da API.

    O catch-all fica registrado depois dos roteadores da API, então uma rota
    conhecida sempre vence; só o que sobra cai no index — que é o
    comportamento esperado de uma SPA.
    """
    index = diretorio / "index.html"
    if not index.is_file():
        raise RuntimeError(
            f"Build do frontend não encontrado em {diretorio}. "
            "Rode `npm run build` em frontend/ ou ajuste FRONTEND_DIR."
        )

    assets = diretorio / "assets"
    if assets.is_dir():
        app.mount(
            "/assets", InterfaceEstatica(directory=assets), name="assets"
        )

    @app.middleware("http")
    async def cabecalhos_de_seguranca(request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        resposta: Response = await call_next(request)
        for nome, valor in CABECALHOS_DE_SEGURANCA.items():
            resposta.headers.setdefault(nome, valor)
        return resposta

    @app.get("/{caminho:path}", include_in_schema=False)
    async def servir_interface(caminho: str) -> Response:
        # Um caminho da API que chegou aqui não existe: devolver o index
        # faria uma chamada de API errada receber HTML com status 200.
        if caminho.startswith(api_prefix.lstrip("/")):
            raise StarletteHTTPException(status_code=404)

        arquivo = diretorio / caminho
        if caminho and arquivo.is_file():
            try:
                arquivo.resolve().relative_to(diretorio.resolve())
            except ValueError:
                raise StarletteHTTPException(status_code=404) from None
            return FileResponse(arquivo)

        return FileResponse(index, headers={"Cache-Control": CACHE_DO_INDEX})
