"""Testes do JobRepository (SQLite)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from ads_varietor.api.repository import (
    SCHEMA_VERSION,
    JobRepository,
    JobStatus,
)


# --- Helpers -------------------------------------------------------------


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "jobs.sqlite3"


@pytest.fixture
async def repository(database_path: Path) -> JobRepository:
    repo = JobRepository(database_path)
    await repo.initialize()
    return repo


def _timestamp_ago(*, hours: float = 0.0, seconds: float = 0.0) -> str:
    momento = datetime.now(timezone.utc) - timedelta(hours=hours, seconds=seconds)
    return momento.isoformat()


def _executar(database_path: Path, sql: str, params: tuple[Any, ...] = ()) -> None:
    """Escreve direto no banco para simular estados difíceis de produzir."""
    connection = sqlite3.connect(database_path)
    try:
        connection.execute(sql, params)
        connection.commit()
    finally:
        connection.close()


def _consultar(
    database_path: Path, sql: str, params: tuple[Any, ...] = ()
) -> list[dict[str, Any]]:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in connection.execute(sql, params).fetchall()]
    finally:
        connection.close()


async def _criar_job(
    repository: JobRepository,
    *,
    job_id: str = "job-1",
    api_key_hash: str = "hash-abc",
    variations: list[tuple[str, dict[str, Any]]] | None = None,
    input_path: Path | None = None,
    output_dir: Path | None = None,
) -> None:
    if variations is None:
        variations = [
            ("var-002", {"crf": 24}),
            ("var-001", {"crf": 23}),
            ("var-003", {"crf": 25}),
        ]
    await repository.create_job(
        job_id=job_id,
        api_key_hash=api_key_hash,
        num_variations=len(variations),
        input_path=input_path or Path("/tmp/entrada.mp4"),
        output_dir=output_dir or Path("/tmp/saida"),
        variations=variations,
    )


# --- Schema --------------------------------------------------------------


async def test_initialize_nao_quebra_quando_executado_duas_vezes(
    database_path: Path,
) -> None:
    """Idempotência: o schema pode ser recriado sem erro nem versão duplicada."""
    repository = JobRepository(database_path)
    await repository.initialize()
    await repository.initialize()

    versoes = _consultar(database_path, "SELECT version FROM schema_version")
    assert versoes == [{"version": SCHEMA_VERSION}]


async def test_initialize_preserva_dados_quando_executado_novamente(
    database_path: Path,
) -> None:
    repository = JobRepository(database_path)
    await repository.initialize()
    await _criar_job(repository)

    await repository.initialize()

    assert await repository.get_job("job-1") is not None


# --- create_job / get_job ------------------------------------------------


async def test_get_job_devolve_variacoes_ordenadas_quando_job_existe(
    repository: JobRepository,
) -> None:
    await _criar_job(repository)

    job = await repository.get_job("job-1")

    assert job is not None
    assert job["job_id"] == "job-1"
    assert job["api_key_hash"] == "hash-abc"
    assert job["status"] == JobStatus.PENDING.value
    assert job["num_variations"] == 3
    assert job["input_path"] == "/tmp/entrada.mp4"
    assert job["output_dir"] == "/tmp/saida"
    assert job["error"] is None
    assert [v["variation_id"] for v in job["variations"]] == [
        "var-001",
        "var-002",
        "var-003",
    ]
    assert [v["status"] for v in job["variations"]] == ["pending"] * 3
    assert job["variations"][0]["params"] == {"crf": 23}
    assert job["variations"][0]["size_bytes"] is None


async def test_get_job_devolve_none_quando_id_inexistente(
    repository: JobRepository,
) -> None:
    assert await repository.get_job("nao-existe") is None


async def test_get_job_isola_variacoes_quando_ha_varios_jobs(
    repository: JobRepository,
) -> None:
    await _criar_job(repository, job_id="job-a", variations=[("a-1", {})])
    await _criar_job(repository, job_id="job-b", variations=[("b-1", {}), ("b-2", {})])

    job_a = await repository.get_job("job-a")
    job_b = await repository.get_job("job-b")

    assert job_a is not None and job_b is not None
    assert [v["variation_id"] for v in job_a["variations"]] == ["a-1"]
    assert [v["variation_id"] for v in job_b["variations"]] == ["b-1", "b-2"]


# --- set_job_status ------------------------------------------------------


@pytest.mark.parametrize(
    "status_inicial",
    [JobStatus.PENDING, JobStatus.RUNNING],
)
async def test_set_job_status_atualiza_quando_estado_nao_terminal(
    repository: JobRepository, status_inicial: JobStatus
) -> None:
    await _criar_job(repository)
    await repository.set_job_status("job-1", status_inicial)

    await repository.set_job_status("job-1", JobStatus.COMPLETED)

    job = await repository.get_job("job-1")
    assert job is not None
    assert job["status"] == JobStatus.COMPLETED.value


async def test_set_job_status_grava_erro_quando_job_falha(
    repository: JobRepository,
) -> None:
    await _criar_job(repository)

    await repository.set_job_status("job-1", JobStatus.FAILED, "ffmpeg morreu")

    job = await repository.get_job("job-1")
    assert job is not None
    assert job["status"] == JobStatus.FAILED.value
    assert job["error"] == "ffmpeg morreu"


async def test_set_job_status_atualiza_updated_at_quando_muda_de_pending(
    repository: JobRepository, database_path: Path
) -> None:
    await _criar_job(repository)
    _executar(
        database_path,
        "UPDATE jobs SET updated_at = ? WHERE job_id = ?",
        (_timestamp_ago(hours=5), "job-1"),
    )
    antes = _consultar(database_path, "SELECT updated_at FROM jobs")[0]["updated_at"]

    await repository.set_job_status("job-1", JobStatus.RUNNING)

    depois = _consultar(database_path, "SELECT updated_at FROM jobs")[0]["updated_at"]
    assert depois > antes


@pytest.mark.parametrize(
    "status_terminal",
    [
        JobStatus.COMPLETED,
        JobStatus.FAILED,
        JobStatus.CANCELLED,
        JobStatus.EXPIRED,
    ],
)
async def test_set_job_status_nao_sobrescreve_quando_estado_ja_e_terminal(
    repository: JobRepository, status_terminal: JobStatus
) -> None:
    """Regressão: DELETE concorrente não pode reverter um terminal já gravado."""
    await _criar_job(repository)
    await repository.set_job_status("job-1", status_terminal, "motivo original")

    await repository.set_job_status("job-1", JobStatus.CANCELLED, "cancelado tarde")
    await repository.set_job_status("job-1", JobStatus.RUNNING)

    job = await repository.get_job("job-1")
    assert job is not None
    assert job["status"] == status_terminal.value
    assert job["error"] == "motivo original"


async def test_set_job_status_nao_cria_job_quando_id_inexistente(
    repository: JobRepository,
) -> None:
    await repository.set_job_status("fantasma", JobStatus.COMPLETED)

    assert await repository.get_job("fantasma") is None


# --- set_variation_result ------------------------------------------------


async def test_set_variation_result_atualiza_status_e_tamanho_quando_conclui(
    repository: JobRepository,
) -> None:
    await _criar_job(repository)

    await repository.set_variation_result(
        job_id="job-1",
        variation_id="var-001",
        status="completed",
        size_bytes=4096,
    )

    job = await repository.get_job("job-1")
    assert job is not None
    variacao = job["variations"][0]
    assert variacao["variation_id"] == "var-001"
    assert variacao["status"] == "completed"
    assert variacao["error"] is None
    assert variacao["size_bytes"] == 4096
    assert job["variations"][1]["status"] == "pending"


async def test_set_variation_result_grava_erro_quando_variacao_falha(
    repository: JobRepository,
) -> None:
    await _criar_job(repository)

    await repository.set_variation_result(
        job_id="job-1",
        variation_id="var-002",
        status="failed",
        error="codec invalido",
    )

    job = await repository.get_job("job-1")
    assert job is not None
    variacao = next(v for v in job["variations"] if v["variation_id"] == "var-002")
    assert variacao["status"] == "failed"
    assert variacao["error"] == "codec invalido"
    assert variacao["size_bytes"] is None


async def test_set_variation_result_atualiza_updated_at_do_job_quando_grava(
    repository: JobRepository, database_path: Path
) -> None:
    await _criar_job(repository)
    _executar(
        database_path,
        "UPDATE jobs SET updated_at = ? WHERE job_id = ?",
        (_timestamp_ago(hours=5), "job-1"),
    )
    antes = _consultar(database_path, "SELECT updated_at FROM jobs")[0]["updated_at"]

    await repository.set_variation_result(
        job_id="job-1", variation_id="var-001", status="completed", size_bytes=1
    )

    depois = _consultar(database_path, "SELECT updated_at FROM jobs")[0]["updated_at"]
    assert depois > antes


# --- fail_unfinished_variations ------------------------------------------


async def test_fail_unfinished_variations_marca_so_pendentes_quando_job_encerra(
    repository: JobRepository,
) -> None:
    """Completed e failed anteriores mantêm status e erro próprios."""
    await _criar_job(
        repository,
        variations=[
            ("var-001", {}),
            ("var-002", {}),
            ("var-003", {}),
            ("var-004", {}),
        ],
    )
    await repository.set_variation_result(
        job_id="job-1", variation_id="var-001", status="completed", size_bytes=999
    )
    await repository.set_variation_result(
        job_id="job-1", variation_id="var-002", status="failed", error="erro proprio"
    )
    await repository.set_variation_result(
        job_id="job-1", variation_id="var-003", status="running"
    )

    await repository.fail_unfinished_variations("job-1", "cancelado pelo usuario")

    job = await repository.get_job("job-1")
    assert job is not None
    por_id = {v["variation_id"]: v for v in job["variations"]}
    assert por_id["var-001"]["status"] == "completed"
    assert por_id["var-001"]["error"] is None
    assert por_id["var-001"]["size_bytes"] == 999
    assert por_id["var-002"]["status"] == "failed"
    assert por_id["var-002"]["error"] == "erro proprio"
    assert por_id["var-003"]["status"] == "failed"
    assert por_id["var-003"]["error"] == "cancelado pelo usuario"
    assert por_id["var-004"]["status"] == "failed"
    assert por_id["var-004"]["error"] == "cancelado pelo usuario"


async def test_fail_unfinished_variations_nao_afeta_outro_job_quando_chamado(
    repository: JobRepository,
) -> None:
    await _criar_job(repository, job_id="job-a", variations=[("a-1", {})])
    await _criar_job(repository, job_id="job-b", variations=[("b-1", {})])

    await repository.fail_unfinished_variations("job-a", "motivo")

    job_b = await repository.get_job("job-b")
    assert job_b is not None
    assert job_b["variations"][0]["status"] == "pending"


# --- fail_interrupted_jobs -----------------------------------------------


async def test_fail_interrupted_jobs_marca_pending_e_running_quando_servico_reinicia(
    repository: JobRepository,
) -> None:
    await _criar_job(repository, job_id="job-pending", variations=[("v", {})])
    await _criar_job(repository, job_id="job-running", variations=[("v", {})])
    await _criar_job(repository, job_id="job-completed", variations=[("v", {})])
    await _criar_job(repository, job_id="job-cancelled", variations=[("v", {})])
    await repository.set_job_status("job-running", JobStatus.RUNNING)
    await repository.set_job_status("job-completed", JobStatus.COMPLETED)
    await repository.set_job_status("job-cancelled", JobStatus.CANCELLED)

    total = await repository.fail_interrupted_jobs()

    assert total == 2
    for job_id, esperado in (
        ("job-pending", JobStatus.FAILED.value),
        ("job-running", JobStatus.FAILED.value),
        ("job-completed", JobStatus.COMPLETED.value),
        ("job-cancelled", JobStatus.CANCELLED.value),
    ):
        job = await repository.get_job(job_id)
        assert job is not None
        assert job["status"] == esperado

    interrompido = await repository.get_job("job-running")
    assert interrompido is not None
    assert interrompido["error"]


async def test_fail_interrupted_jobs_devolve_zero_quando_nao_ha_job_ativo(
    repository: JobRepository,
) -> None:
    await _criar_job(repository, job_id="job-ok", variations=[("v", {})])
    await repository.set_job_status("job-ok", JobStatus.COMPLETED)

    assert await repository.fail_interrupted_jobs() == 0


# --- list_expired_jobs / mark_expired ------------------------------------


async def _envelhecer(database_path: Path, job_id: str, horas: float) -> None:
    _executar(
        database_path,
        "UPDATE jobs SET updated_at = ? WHERE job_id = ?",
        (_timestamp_ago(hours=horas), job_id),
    )


async def test_list_expired_jobs_devolve_so_terminal_antigo_quando_ha_mistura(
    repository: JobRepository, database_path: Path
) -> None:
    """Regressão: job ainda rodando não pode ter os arquivos apagados."""
    cenarios = {
        "job-completed-antigo": JobStatus.COMPLETED,
        "job-failed-antigo": JobStatus.FAILED,
        "job-cancelled-antigo": JobStatus.CANCELLED,
        "job-running-antigo": JobStatus.RUNNING,
        "job-pending-antigo": None,
    }
    for job_id, status in cenarios.items():
        await _criar_job(repository, job_id=job_id, variations=[("v", {})])
        if status is not None:
            await repository.set_job_status(job_id, status)
        await _envelhecer(database_path, job_id, horas=48)

    await _criar_job(repository, job_id="job-completed-novo", variations=[("v", {})])
    await repository.set_job_status("job-completed-novo", JobStatus.COMPLETED)

    expirados = await repository.list_expired_jobs(retention_hours=24)

    assert {item["job_id"] for item in expirados} == {
        "job-completed-antigo",
        "job-failed-antigo",
        "job-cancelled-antigo",
    }
    assert expirados[0]["input_path"] == "/tmp/entrada.mp4"
    assert expirados[0]["output_dir"] == "/tmp/saida"


async def test_list_expired_jobs_nao_devolve_nada_quando_todos_sao_recentes(
    repository: JobRepository,
) -> None:
    await _criar_job(repository, job_id="job-1", variations=[("v", {})])
    await repository.set_job_status("job-1", JobStatus.COMPLETED)

    assert await repository.list_expired_jobs(retention_hours=24) == []


async def test_list_expired_jobs_ignora_job_ja_expirado_quando_reexecutado(
    repository: JobRepository, database_path: Path
) -> None:
    await _criar_job(repository, job_id="job-1", variations=[("v", {})])
    await repository.set_job_status("job-1", JobStatus.COMPLETED)
    await repository.mark_expired("job-1")
    await _envelhecer(database_path, "job-1", horas=48)

    assert await repository.list_expired_jobs(retention_hours=24) == []


async def test_mark_expired_muda_status_e_remove_variacoes_quando_chamado(
    repository: JobRepository,
) -> None:
    await _criar_job(repository)
    await repository.set_job_status("job-1", JobStatus.COMPLETED)

    await repository.mark_expired("job-1")

    job = await repository.get_job("job-1")
    assert job is not None
    assert job["status"] == JobStatus.EXPIRED.value
    assert job["variations"] == []


async def test_mark_expired_preserva_variacoes_de_outro_job_quando_chamado(
    repository: JobRepository,
) -> None:
    await _criar_job(repository, job_id="job-a", variations=[("a-1", {})])
    await _criar_job(repository, job_id="job-b", variations=[("b-1", {})])

    await repository.mark_expired("job-a")

    job_b = await repository.get_job("job-b")
    assert job_b is not None
    assert len(job_b["variations"]) == 1


# --- count_and_record_event ----------------------------------------------


async def test_count_and_record_event_bloqueia_quando_limite_atingido_na_janela(
    repository: JobRepository,
) -> None:
    for _ in range(3):
        permitido = await repository.count_and_record_event(
            api_key_hash="hash-a",
            event_type="job_create",
            window_seconds=60,
            limit=3,
        )
        assert permitido is True

    assert (
        await repository.count_and_record_event(
            api_key_hash="hash-a",
            event_type="job_create",
            window_seconds=60,
            limit=3,
        )
        is False
    )


async def test_count_and_record_event_permite_quando_evento_esta_fora_da_janela(
    repository: JobRepository, database_path: Path
) -> None:
    """Evento antigo não conta para a janela corrente."""
    assert await repository.count_and_record_event(
        api_key_hash="hash-a", event_type="job_create", window_seconds=60, limit=1
    )
    _executar(
        database_path,
        "UPDATE rate_limit_events SET created_at = ?",
        (_timestamp_ago(seconds=300),),
    )

    assert await repository.count_and_record_event(
        api_key_hash="hash-a", event_type="job_create", window_seconds=60, limit=1
    )


async def test_count_and_record_event_nao_registra_quando_bloqueado(
    repository: JobRepository, database_path: Path
) -> None:
    await repository.count_and_record_event(
        api_key_hash="hash-a", event_type="job_create", window_seconds=60, limit=1
    )
    await repository.count_and_record_event(
        api_key_hash="hash-a", event_type="job_create", window_seconds=60, limit=1
    )

    total = _consultar(
        database_path, "SELECT COUNT(*) AS total FROM rate_limit_events"
    )[0]["total"]
    assert total == 1


async def test_count_and_record_event_conta_separado_quando_chaves_diferentes(
    repository: JobRepository,
) -> None:
    assert await repository.count_and_record_event(
        api_key_hash="hash-a", event_type="job_create", window_seconds=60, limit=1
    )
    assert (
        await repository.count_and_record_event(
            api_key_hash="hash-a", event_type="job_create", window_seconds=60, limit=1
        )
        is False
    )

    assert await repository.count_and_record_event(
        api_key_hash="hash-b", event_type="job_create", window_seconds=60, limit=1
    )


async def test_count_and_record_event_conta_separado_quando_tipos_diferentes(
    repository: JobRepository,
) -> None:
    assert await repository.count_and_record_event(
        api_key_hash="hash-a", event_type="job_create", window_seconds=60, limit=1
    )
    assert (
        await repository.count_and_record_event(
            api_key_hash="hash-a", event_type="job_create", window_seconds=60, limit=1
        )
        is False
    )

    assert await repository.count_and_record_event(
        api_key_hash="hash-a", event_type="upload", window_seconds=60, limit=1
    )


async def test_count_and_record_event_bloqueia_sempre_quando_limite_zero(
    repository: JobRepository,
) -> None:
    assert (
        await repository.count_and_record_event(
            api_key_hash="hash-a", event_type="job_create", window_seconds=60, limit=0
        )
        is False
    )


# --- Contabilidade de uso por chave --------------------------------------


async def test_bytes_used_by_key_soma_saidas_e_entrada_do_job_pendente(
    repository: JobRepository, database_path: Path
) -> None:
    await _criar_job(
        repository,
        job_id="job-1",
        api_key_hash="hash-a",
        variations=[("var-001", {}), ("var-002", {})],
    )
    _executar(
        database_path,
        "UPDATE jobs SET input_bytes = 1000 WHERE job_id = ?",
        ("job-1",),
    )
    await repository.set_variation_result(
        job_id="job-1", variation_id="var-001", status="completed", size_bytes=500
    )

    # Job ainda pendente: a entrada continua em disco e precisa contar.
    assert await repository.bytes_used_by_key("hash-a") == 1500


async def test_bytes_used_by_key_para_de_contar_a_entrada_apos_o_termino(
    repository: JobRepository, database_path: Path
) -> None:
    """Depois de terminar, o upload foi apagado — cobrar por ele seria erro."""
    await _criar_job(
        repository, job_id="job-1", api_key_hash="hash-a", variations=[("var-001", {})]
    )
    _executar(
        database_path,
        "UPDATE jobs SET input_bytes = 1000 WHERE job_id = ?",
        ("job-1",),
    )
    await repository.set_variation_result(
        job_id="job-1", variation_id="var-001", status="completed", size_bytes=700
    )
    await repository.set_job_status("job-1", JobStatus.COMPLETED)

    assert await repository.bytes_used_by_key("hash-a") == 700


async def test_bytes_used_by_key_ignora_job_expirado(
    repository: JobRepository,
) -> None:
    await _criar_job(
        repository, job_id="job-1", api_key_hash="hash-a", variations=[("var-001", {})]
    )
    await repository.set_variation_result(
        job_id="job-1", variation_id="var-001", status="completed", size_bytes=900
    )
    await repository.set_job_status("job-1", JobStatus.COMPLETED)
    await repository.mark_expired("job-1")

    assert await repository.bytes_used_by_key("hash-a") == 0


async def test_bytes_used_by_key_nao_mistura_chaves(
    repository: JobRepository,
) -> None:
    await _criar_job(
        repository, job_id="job-a", api_key_hash="hash-a", variations=[("var-001", {})]
    )
    await _criar_job(
        repository, job_id="job-b", api_key_hash="hash-b", variations=[("var-001", {})]
    )
    await repository.set_variation_result(
        job_id="job-a", variation_id="var-001", status="completed", size_bytes=100
    )
    await repository.set_variation_result(
        job_id="job-b", variation_id="var-001", status="completed", size_bytes=999999
    )

    assert await repository.bytes_used_by_key("hash-a") == 100


async def test_bytes_used_by_key_e_zero_para_chave_sem_job(
    repository: JobRepository,
) -> None:
    assert await repository.bytes_used_by_key("hash-desconhecido") == 0


async def test_count_jobs_by_status_agrupa_no_servico_inteiro(
    repository: JobRepository,
) -> None:
    await _criar_job(repository, job_id="job-a", api_key_hash="hash-a")
    await _criar_job(repository, job_id="job-b", api_key_hash="hash-b")
    await repository.set_job_status("job-b", JobStatus.COMPLETED)

    assert await repository.count_jobs_by_status() == {
        "pending": 1,
        "completed": 1,
    }


async def test_count_jobs_by_status_filtra_por_chave_quando_informada(
    repository: JobRepository,
) -> None:
    await _criar_job(repository, job_id="job-a", api_key_hash="hash-a")
    await _criar_job(repository, job_id="job-b", api_key_hash="hash-b")

    assert await repository.count_jobs_by_status("hash-a") == {"pending": 1}


# --- Apoio à reconciliação -----------------------------------------------


async def test_job_ids_com_diretorio_esperado_exclui_os_expirados(
    repository: JobRepository,
) -> None:
    await _criar_job(repository, job_id="job-vivo", api_key_hash="hash-a")
    await _criar_job(repository, job_id="job-morto", api_key_hash="hash-a")
    await repository.set_job_status("job-morto", JobStatus.COMPLETED)
    await repository.mark_expired("job-morto")

    assert await repository.job_ids_with_expected_directory() == {"job-vivo"}


async def test_list_completed_jobs_traz_so_os_concluidos(
    repository: JobRepository,
) -> None:
    await _criar_job(repository, job_id="job-ok", api_key_hash="hash-a")
    await _criar_job(repository, job_id="job-pendente", api_key_hash="hash-a")
    await repository.set_job_status("job-ok", JobStatus.COMPLETED)

    concluidos = await repository.list_completed_jobs()

    assert [item["job_id"] for item in concluidos] == ["job-ok"]


async def test_active_input_paths_traz_so_jobs_nao_terminados(
    repository: JobRepository, tmp_path: Path
) -> None:
    await _criar_job(
        repository,
        job_id="job-ativo",
        api_key_hash="hash-a",
        input_path=tmp_path / "ativo.mp4",
    )
    await _criar_job(
        repository,
        job_id="job-morto",
        api_key_hash="hash-a",
        input_path=tmp_path / "morto.mp4",
    )
    await repository.set_job_status("job-morto", JobStatus.COMPLETED)

    assert await repository.active_input_paths() == {str(tmp_path / "ativo.mp4")}


# ---------------------------------------------------------------------------
# Migração de schema
# ---------------------------------------------------------------------------

SCHEMA_V1 = """
CREATE TABLE schema_version (version INTEGER NOT NULL);
INSERT INTO schema_version (version) VALUES (1);
CREATE TABLE jobs (
  job_id TEXT PRIMARY KEY, api_key_hash TEXT NOT NULL, status TEXT NOT NULL,
  num_variations INTEGER NOT NULL, input_path TEXT NOT NULL,
  output_dir TEXT NOT NULL, error TEXT, created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL);
CREATE TABLE variations (
  job_id TEXT NOT NULL, variation_id TEXT NOT NULL, status TEXT NOT NULL,
  params_json TEXT NOT NULL, error TEXT, size_bytes INTEGER,
  PRIMARY KEY (job_id, variation_id));
CREATE TABLE rate_limit_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, api_key_hash TEXT NOT NULL,
  event_type TEXT NOT NULL, created_at TEXT NOT NULL);
INSERT INTO jobs VALUES
  ('job_antigo','hash_a','completed',2,'/tmp/e.mp4','/tmp/s',NULL,
   '2026-01-01T00:00:00+00:00','2026-01-01T00:00:00+00:00');
INSERT INTO variations VALUES
  ('job_antigo','var_0000','completed','{}',NULL,100);
"""


async def test_banco_antigo_ganha_as_colunas_novas_quando_inicializado(
    tmp_path: Path,
) -> None:
    """Regressão: `CREATE TABLE IF NOT EXISTS` não altera tabela existente.

    Sem a lista de colunas aditivas, um banco já em uso continuava sem
    `mode`, `source_md5`, `input_bytes` e `md5`, e toda consulta quebrava.
    """
    import sqlite3

    caminho = tmp_path / "v1.sqlite3"
    conexao = sqlite3.connect(caminho)
    conexao.executescript(SCHEMA_V1)
    conexao.commit()
    conexao.close()

    repositorio = JobRepository(caminho)
    await repositorio.initialize()

    job = await repositorio.get_job("job_antigo")

    assert job is not None
    # Dados antigos preservados.
    assert job["status"] == "completed"
    assert job["num_variations"] == 2
    # Colunas novas presentes, com o default declarado.
    assert job["mode"] == "full"
    assert job["source_md5"] is None
    assert job["input_bytes"] is None
    assert job["variations"][0]["md5"] is None


async def test_migracao_e_idempotente_quando_roda_duas_vezes(
    tmp_path: Path,
) -> None:
    import sqlite3

    caminho = tmp_path / "v1.sqlite3"
    conexao = sqlite3.connect(caminho)
    conexao.executescript(SCHEMA_V1)
    conexao.commit()
    conexao.close()

    repositorio = JobRepository(caminho)
    await repositorio.initialize()
    await repositorio.initialize()

    assert await repositorio.get_job("job_antigo") is not None
