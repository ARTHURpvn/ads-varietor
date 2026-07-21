"""Log estruturado em JSON para as operações críticas do serviço.

Uma linha JSON por evento é o que permite responder, meses depois, "quando
o disco encheu e por quê" sem precisar de um parser de texto livre.

Regra inegociável: nenhum campo aqui pode carregar API key nem o nome do
arquivo enviado pelo usuário. Os helpers só aceitam os campos declarados,
e o identificador de dono é sempre um prefixo curto do hash da chave —
suficiente para correlacionar, insuficiente para reconstruir a chave.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Final

# Campos que o logging.LogRecord já traz; qualquer chave fora desta lista
# no __dict__ do record foi colocada por nós via `extra=`.
_RESERVED_RECORD_FIELDS: Final[frozenset[str]] = frozenset(
    logging.LogRecord("", 0, "", 0, "", None, None).__dict__
) | {"message", "asctime", "taskName"}

# Prefixo do hash usado como identificador de dono nos logs. 12 hex = 48
# bits: colide na prática nunca, e não permite força bruta reversa útil.
OWNER_PREFIX_LENGTH: Final[int] = 12


class JsonLogFormatter(logging.Formatter):
    """Serializa cada registro de log como um objeto JSON de uma linha."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        for key, value in record.__dict__.items():
            if key not in _RESERVED_RECORD_FIELDS:
                payload[key] = value

        if record.exc_info is not None:
            # Só o tipo da exceção: o traceback fica no handler padrão de
            # erro, e não deve poluir o evento estruturado.
            exc_type = record.exc_info[0]
            payload["exception"] = (
                exc_type.__name__ if exc_type else "Exception"
            )

        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(*, level: str = "INFO", json_output: bool = True) -> None:
    """Instala o formatador escolhido no logger raiz.

    Idempotente: chamar de novo troca o formatador em vez de empilhar
    handlers, o que duplicaria toda linha de log.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(
        JsonLogFormatter()
        if json_output
        else logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )

    root = logging.getLogger()
    for existente in list(root.handlers):
        root.removeHandler(existente)
    root.addHandler(handler)
    root.setLevel(level.upper())


def owner_id(api_key_hash: str) -> str:
    """Identificador curto e estável do dono, derivado do hash da chave.

    Nunca receba aqui a chave em texto puro: o parâmetro é o hash que a
    autenticação já produziu.
    """
    return api_key_hash[:OWNER_PREFIX_LENGTH]


def log_event(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    job_id: str | None = None,
    owner: str | None = None,
    duration_seconds: float | None = None,
    bytes_total: int | None = None,
    **extras: Any,
) -> None:
    """Emite um evento estruturado.

    Os campos são explícitos de propósito: um `**kwargs` solto convidaria
    a logar o nome do arquivo ou a chave por descuido.
    """
    campos: dict[str, Any] = {"event": event}
    if job_id is not None:
        campos["job_id"] = job_id
    if owner is not None:
        campos["owner"] = owner
    if duration_seconds is not None:
        campos["duration_seconds"] = round(duration_seconds, 3)
    if bytes_total is not None:
        campos["bytes"] = bytes_total
    campos.update(extras)

    logger.log(level, event, extra=campos)
