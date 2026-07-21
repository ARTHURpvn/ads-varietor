"""Testes de src/ads_varietor/api/observability.py.

O ponto crítico não é o formato: é a garantia de que a API key em texto
puro e o nome do arquivo enviado nunca chegam ao log.
"""

from __future__ import annotations

import hashlib
import json
import logging

import pytest

from ads_varietor.api.observability import (
    OWNER_PREFIX_LENGTH,
    JsonLogFormatter,
    configure_logging,
    log_event,
    owner_id,
)


def _registro(**kwargs: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="teste",
        level=logging.INFO,
        pathname="arquivo.py",
        lineno=1,
        msg="mensagem",
        args=None,
        exc_info=None,
    )
    for chave, valor in kwargs.items():
        setattr(record, chave, valor)
    return record


# --- Formatador ----------------------------------------------------------


def test_formatador_produz_json_de_uma_linha_valido() -> None:
    saida = JsonLogFormatter().format(_registro())

    assert "\n" not in saida
    corpo = json.loads(saida)
    assert corpo["message"] == "mensagem"
    assert corpo["level"] == "INFO"
    assert corpo["logger"] == "teste"
    assert corpo["timestamp"]


def test_formatador_promove_campos_extras_para_o_topo_do_json() -> None:
    saida = JsonLogFormatter().format(_registro(event="job.created", bytes=42))

    corpo = json.loads(saida)
    assert corpo["event"] == "job.created"
    assert corpo["bytes"] == 42


def test_formatador_nao_inclui_campos_internos_do_logrecord() -> None:
    corpo = json.loads(JsonLogFormatter().format(_registro()))

    for interno in ("pathname", "lineno", "args", "msg", "levelno"):
        assert interno not in corpo


def test_formatador_serializa_valor_nao_json_sem_estourar() -> None:
    saida = JsonLogFormatter().format(_registro(objeto=object()))

    assert isinstance(json.loads(saida)["objeto"], str)


def test_formatador_registra_so_o_tipo_da_excecao() -> None:
    try:
        raise ValueError("detalhe interno que não deve vazar")
    except ValueError:
        import sys

        record = _registro()
        record.exc_info = sys.exc_info()
        corpo = json.loads(JsonLogFormatter().format(record))

    assert corpo["exception"] == "ValueError"
    assert "detalhe interno" not in json.dumps(corpo)


# --- Identificador de dono -----------------------------------------------


def test_owner_id_encurta_o_hash_sem_revelar_a_chave() -> None:
    chave = "chave-secreta-de-teste-com-tamanho-suficiente"
    hash_da_chave = hashlib.sha256(chave.encode("utf-8")).hexdigest()

    identificador = owner_id(hash_da_chave)

    assert len(identificador) == OWNER_PREFIX_LENGTH
    assert identificador != hash_da_chave
    assert chave not in identificador


def test_owner_id_e_estavel_para_a_mesma_chave() -> None:
    hash_da_chave = hashlib.sha256(b"mesma-chave").hexdigest()

    assert owner_id(hash_da_chave) == owner_id(hash_da_chave)


# --- log_event -----------------------------------------------------------


def test_log_event_emite_os_campos_declarados(
    caplog: pytest.LogCaptureFixture,
) -> None:
    logger = logging.getLogger("teste.log_event")

    with caplog.at_level(logging.INFO, logger="teste.log_event"):
        log_event(
            logger,
            "job.completed",
            job_id="abc123",
            owner="0011223344ff",
            duration_seconds=1.23456,
            bytes_total=2048,
        )

    record = caplog.records[-1]
    assert record.event == "job.completed"
    assert record.job_id == "abc123"
    assert record.owner == "0011223344ff"
    assert record.duration_seconds == 1.235
    assert record.bytes == 2048


def test_log_event_omite_campos_nao_informados(
    caplog: pytest.LogCaptureFixture,
) -> None:
    logger = logging.getLogger("teste.log_event_vazio")

    with caplog.at_level(logging.INFO, logger="teste.log_event_vazio"):
        log_event(logger, "cleanup.retention")

    record = caplog.records[-1]
    assert record.event == "cleanup.retention"
    assert not hasattr(record, "job_id")
    assert not hasattr(record, "bytes")


def test_log_event_respeita_o_nivel_informado(
    caplog: pytest.LogCaptureFixture,
) -> None:
    logger = logging.getLogger("teste.log_event_nivel")

    with caplog.at_level(logging.WARNING, logger="teste.log_event_nivel"):
        log_event(
            logger, "storage.threshold_exceeded", level=logging.WARNING
        )

    assert caplog.records[-1].levelno == logging.WARNING


# --- configure_logging ---------------------------------------------------


def test_configure_logging_nao_empilha_handlers_ao_ser_chamado_de_novo() -> None:
    raiz = logging.getLogger()
    handlers_originais = list(raiz.handlers)
    nivel_original = raiz.level
    try:
        configure_logging(level="INFO", json_output=True)
        depois_da_primeira = len(raiz.handlers)
        configure_logging(level="INFO", json_output=True)

        assert len(raiz.handlers) == depois_da_primeira == 1
        assert isinstance(raiz.handlers[0].formatter, JsonLogFormatter)
    finally:
        for handler in list(raiz.handlers):
            raiz.removeHandler(handler)
        for handler in handlers_originais:
            raiz.addHandler(handler)
        raiz.setLevel(nivel_original)


def test_configure_logging_usa_formato_texto_quando_json_desligado() -> None:
    raiz = logging.getLogger()
    handlers_originais = list(raiz.handlers)
    nivel_original = raiz.level
    try:
        configure_logging(level="DEBUG", json_output=False)

        assert not isinstance(raiz.handlers[0].formatter, JsonLogFormatter)
        assert raiz.level == logging.DEBUG
    finally:
        for handler in list(raiz.handlers):
            raiz.removeHandler(handler)
        for handler in handlers_originais:
            raiz.addHandler(handler)
        raiz.setLevel(nivel_original)
