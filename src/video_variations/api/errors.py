"""Erros HTTP no formato RFC 9457 (application/problem+json).

As mensagens são escritas para o usuário final: nunca contêm caminho de
sistema de arquivos, stack trace ou saída crua do FFmpeg.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

PROBLEM_CONTENT_TYPE = "application/problem+json"


class ProblemError(Exception):
    """Erro que vira uma resposta problem+json."""

    def __init__(
        self,
        *,
        status: int,
        title: str,
        detail: str,
        problem_type: str = "about:blank",
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(detail)
        self.status = status
        self.title = title
        self.detail = detail
        self.problem_type = problem_type
        self.headers = headers or {}

    def to_response(self) -> JSONResponse:
        payload: dict[str, Any] = {
            "type": self.problem_type,
            "title": self.title,
            "status": self.status,
            "detail": self.detail,
        }
        return JSONResponse(
            payload,
            status_code=self.status,
            media_type=PROBLEM_CONTENT_TYPE,
            headers=self.headers,
        )


async def problem_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ProblemError)
    return exc.to_response()


async def unhandled_error_handler(_: Request, __: Exception) -> JSONResponse:
    """Converte qualquer exceção não tratada numa resposta genérica.

    O detalhe real fica só no log do servidor — devolvê-lo ao cliente
    vazaria estrutura interna.
    """
    return ProblemError(
        status=500,
        title="Erro interno",
        detail="Não foi possível concluir a operação. Tente novamente.",
    ).to_response()


def unauthorized() -> ProblemError:
    return ProblemError(
        status=401,
        title="Credencial ausente ou inválida",
        detail="Requisição não autorizada.",
    )


def job_not_found() -> ProblemError:
    return ProblemError(
        status=404,
        title="Job não encontrado",
        detail="Nenhum job com esse identificador.",
    )


def invalid_video() -> ProblemError:
    return ProblemError(
        status=400,
        title="Arquivo inválido",
        detail="Envie um arquivo de vídeo (MP4, MOV ou WebM).",
    )


def upload_too_large(max_bytes: int) -> ProblemError:
    megabytes = max_bytes // (1024 * 1024)
    return ProblemError(
        status=413,
        title="Arquivo muito grande",
        detail=f"O vídeo excede o limite de {megabytes} MB.",
    )


def rate_limited(retry_after_seconds: int) -> ProblemError:
    return ProblemError(
        status=429,
        title="Limite de uso atingido",
        detail="Muitas requisições. Aguarde um pouco e tente de novo.",
        headers={"Retry-After": str(retry_after_seconds)},
    )


def storage_full() -> ProblemError:
    return ProblemError(
        status=507,
        title="Sem espaço disponível",
        detail="O serviço está sem espaço para novos vídeos. Tente mais tarde.",
    )


def invalid_identifier() -> ProblemError:
    return ProblemError(
        status=400,
        title="Identificador inválido",
        detail="O identificador informado não é válido.",
    )
