"""Persistência dos jobs em SQLite.

O SQLite é a fonte de verdade: o estado precisa sobreviver a um restart do
processo. Todo SQL usa placeholders — nunca interpolação de string.
"""

from __future__ import annotations

import asyncio
import enum
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 2

# Colunas adicionadas depois da versão 1. Bancos criados antes disso ganham
# a coluna por ALTER TABLE no start; recriar a tabela perderia os jobs.
# Colunas acrescentadas depois da v1 do schema. `CREATE TABLE IF NOT EXISTS`
# não altera tabela existente, então toda coluna nova precisa estar aqui —
# senão um banco já em uso continua sem ela e as queries quebram.
ADDITIVE_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("jobs", "mode", "TEXT NOT NULL DEFAULT 'full'"),
    ("jobs", "source_md5", "TEXT"),
    ("jobs", "input_bytes", "INTEGER"),
    ("variations", "md5", "TEXT"),
    ("variations", "progress", "REAL NOT NULL DEFAULT 0"),
)

SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS jobs (
        job_id          TEXT PRIMARY KEY,
        api_key_hash    TEXT NOT NULL,
        status          TEXT NOT NULL,
        num_variations  INTEGER NOT NULL,
        mode            TEXT NOT NULL DEFAULT 'full',
        source_md5      TEXT,
        input_path      TEXT NOT NULL,
        input_bytes     INTEGER,
        output_dir      TEXT NOT NULL,
        error           TEXT,
        created_at      TEXT NOT NULL,
        updated_at      TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS variations (
        job_id       TEXT NOT NULL,
        variation_id TEXT NOT NULL,
        status       TEXT NOT NULL,
        params_json  TEXT NOT NULL,
        error        TEXT,
        size_bytes   INTEGER,
        md5          TEXT,
        progress     REAL NOT NULL DEFAULT 0,
        PRIMARY KEY (job_id, variation_id),
        FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rate_limit_events (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        api_key_hash TEXT NOT NULL,
        event_type   TEXT NOT NULL,
        created_at   TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_jobs_key ON jobs(api_key_hash)",
    "CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, created_at)",
    """
    CREATE INDEX IF NOT EXISTS idx_rate_events
        ON rate_limit_events(api_key_hash, event_type, created_at)
    """,
)


class JobStatus(str, enum.Enum):
    """Estados possíveis de um job. Estado terminal nunca retrocede."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"

    @property
    def is_terminal(self) -> bool:
        return self in _TERMINAL_STATUSES


_TERMINAL_STATUSES = frozenset(
    {
        JobStatus.COMPLETED,
        JobStatus.FAILED,
        JobStatus.CANCELLED,
        JobStatus.EXPIRED,
    }
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobRepository:
    """Acesso ao banco de jobs.

    Os métodos são assíncronos e delegam o SQL para uma thread: as queries
    são curtas, mas o event loop não pode esperar por I/O de disco.
    """

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._database_path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=10000")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    # --- Schema ----------------------------------------------------------

    def initialize_sync(self) -> None:
        """Cria o schema, aplica migrações aditivas e registra a versão.

        Idempotente: pode rodar a cada start do processo.
        """
        with self._connect() as connection:
            for statement in SCHEMA_STATEMENTS:
                connection.execute(statement)
            self._apply_additive_columns(connection)

            row = connection.execute("SELECT version FROM schema_version").fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO schema_version (version) VALUES (?)",
                    (SCHEMA_VERSION,),
                )
            elif int(row["version"]) < SCHEMA_VERSION:
                connection.execute(
                    "UPDATE schema_version SET version = ?", (SCHEMA_VERSION,)
                )

    @staticmethod
    def _apply_additive_columns(connection: sqlite3.Connection) -> None:
        """Adiciona colunas novas em bancos criados por versões anteriores.

        Os nomes vêm de uma constante do módulo, nunca de entrada externa —
        `ALTER TABLE` não aceita placeholder para identificador.
        """
        for tabela, coluna, tipo in ADDITIVE_COLUMNS:
            existentes = {
                str(linha["name"])
                for linha in connection.execute(f"PRAGMA table_info({tabela})")
            }
            if coluna not in existentes:
                connection.execute(
                    f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}"
                )

    async def initialize(self) -> None:
        await asyncio.to_thread(self.initialize_sync)

    # --- Escrita ---------------------------------------------------------

    def _create_job_sync(
        self,
        *,
        job_id: str,
        api_key_hash: str,
        num_variations: int,
        input_path: Path,
        mode: str = "full",
        source_md5: str | None = None,
        input_bytes: int | None = None,
        output_dir: Path,
        variations: list[tuple[str, dict[str, Any]]],
    ) -> None:
        timestamp = _now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO jobs (
                    job_id, api_key_hash, status, num_variations, mode,
                    source_md5, input_path, input_bytes, output_dir,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    api_key_hash,
                    JobStatus.PENDING.value,
                    num_variations,
                    mode,
                    source_md5,
                    str(input_path),
                    input_bytes,
                    str(output_dir),
                    timestamp,
                    timestamp,
                ),
            )
            connection.executemany(
                """
                INSERT INTO variations (job_id, variation_id, status, params_json)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (job_id, variation_id, "pending", json.dumps(params))
                    for variation_id, params in variations
                ],
            )

    async def create_job(
        self,
        *,
        job_id: str,
        api_key_hash: str,
        num_variations: int,
        input_path: Path,
        mode: str = "full",
        source_md5: str | None = None,
        input_bytes: int | None = None,
        output_dir: Path,
        variations: list[tuple[str, dict[str, Any]]],
    ) -> None:
        await asyncio.to_thread(
            self._create_job_sync,
            job_id=job_id,
            api_key_hash=api_key_hash,
            num_variations=num_variations,
            mode=mode,
            source_md5=source_md5,
            input_bytes=input_bytes,
            input_path=input_path,
            output_dir=output_dir,
            variations=variations,
        )

    def _set_job_status_sync(
        self, job_id: str, status: JobStatus, error: str | None
    ) -> None:
        terminais = [item.value for item in _TERMINAL_STATUSES]
        marcadores = ", ".join("?" for _ in terminais)
        with self._connect() as connection:
            # A guarda impede que um DELETE que chega no exato momento em que
            # o job termina sobrescreva COMPLETED com CANCELLED. Estado
            # terminal não retrocede.
            connection.execute(
                f"""
                UPDATE jobs
                   SET status = ?, error = ?, updated_at = ?
                 WHERE job_id = ? AND status NOT IN ({marcadores})
                """,
                (status.value, error, _now(), job_id, *terminais),
            )

    async def set_job_status(
        self, job_id: str, status: JobStatus, error: str | None = None
    ) -> None:
        await asyncio.to_thread(self._set_job_status_sync, job_id, status, error)

    def _set_variation_progress_sync(
        self, job_id: str, variation_id: str, progress: float
    ) -> None:
        with self._connect() as connection:
            # `progress >= ?` impede que um bloco atrasado do FFmpeg faça a
            # barra andar para trás na tela.
            connection.execute(
                """
                UPDATE variations
                   SET status = 'running', progress = ?
                 WHERE job_id = ? AND variation_id = ?
                   AND status IN ('pending', 'running')
                   AND progress <= ?
                """,
                (progress, job_id, variation_id, progress),
            )

    async def set_variation_progress(
        self, *, job_id: str, variation_id: str, progress: float
    ) -> None:
        """Grava a fração concluída de uma variação em andamento."""
        await asyncio.to_thread(
            self._set_variation_progress_sync, job_id, variation_id, progress
        )

    def _fail_unfinished_variations_sync(self, job_id: str, reason: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE variations
                   SET status = 'failed', error = ?
                 WHERE job_id = ? AND status IN ('pending', 'running')
                """,
                (reason, job_id),
            )

    async def fail_unfinished_variations(self, job_id: str, reason: str) -> None:
        """Encerra as variações que não chegaram a concluir."""
        await asyncio.to_thread(
            self._fail_unfinished_variations_sync, job_id, reason
        )

    def _set_variation_result_sync(
        self,
        job_id: str,
        variation_id: str,
        status: str,
        error: str | None,
        size_bytes: int | None,
        md5: str | None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE variations
                   SET status = ?, error = ?, size_bytes = ?, md5 = ?
                 WHERE job_id = ? AND variation_id = ?
                """,
                (status, error, size_bytes, md5, job_id, variation_id),
            )
            connection.execute(
                "UPDATE jobs SET updated_at = ? WHERE job_id = ?", (_now(), job_id)
            )

    async def set_variation_result(
        self,
        *,
        job_id: str,
        variation_id: str,
        status: str,
        error: str | None = None,
        size_bytes: int | None = None,
        md5: str | None = None,
    ) -> None:
        await asyncio.to_thread(
            self._set_variation_result_sync,
            job_id,
            variation_id,
            status,
            error,
            size_bytes,
            md5,
        )

    # --- Leitura ---------------------------------------------------------

    def _get_job_sync(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            job_row = connection.execute(
                "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            if job_row is None:
                return None
            variation_rows = connection.execute(
                """
                SELECT variation_id, status, params_json, error, size_bytes,
                       md5, progress
                  FROM variations
                 WHERE job_id = ?
                 ORDER BY variation_id
                """,
                (job_id,),
            ).fetchall()

        job = dict(job_row)
        job["variations"] = [
            {
                "variation_id": row["variation_id"],
                "status": row["status"],
                "params": json.loads(row["params_json"]),
                "error": row["error"],
                "size_bytes": row["size_bytes"],
                "md5": row["md5"],
                # Uma variação que terminou vale 100%, mesmo que o último
                # bloco de progresso não tenha chegado antes do fim.
                "progress": (
                    1.0
                    if row["status"] in {"completed", "failed"}
                    else float(row["progress"] or 0.0)
                ),
            }
            for row in variation_rows
        ]
        return job

    async def get_job(self, job_id: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._get_job_sync, job_id)

    # --- Manutenção ------------------------------------------------------

    def _fail_interrupted_jobs_sync(self) -> int:
        """Marca como falhos os jobs que estavam rodando quando o processo caiu."""
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs
                   SET status = ?, error = ?, updated_at = ?
                 WHERE status IN (?, ?)
                """,
                (
                    JobStatus.FAILED.value,
                    "Processamento interrompido por reinício do serviço.",
                    _now(),
                    JobStatus.PENDING.value,
                    JobStatus.RUNNING.value,
                ),
            )
            return cursor.rowcount

    async def fail_interrupted_jobs(self) -> int:
        return await asyncio.to_thread(self._fail_interrupted_jobs_sync)

    def _list_expired_jobs_sync(self, retention_hours: int) -> list[dict[str, str]]:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(hours=retention_hours)
        ).isoformat()
        with self._connect() as connection:
            # Só job já terminado é candidato à expiração. Sem esse filtro, um
            # job ainda renderizando teria os arquivos apagados debaixo do
            # FFmpeg em execução.
            rows = connection.execute(
                """
                SELECT job_id, input_path, output_dir
                  FROM jobs
                 WHERE status IN (?, ?, ?) AND updated_at < ?
                """,
                (
                    JobStatus.COMPLETED.value,
                    JobStatus.FAILED.value,
                    JobStatus.CANCELLED.value,
                    cutoff,
                ),
            ).fetchall()
        return [dict(row) for row in rows]

    async def list_expired_jobs(self, retention_hours: int) -> list[dict[str, str]]:
        return await asyncio.to_thread(self._list_expired_jobs_sync, retention_hours)

    def _mark_expired_sync(self, job_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE jobs SET status = ?, updated_at = ? WHERE job_id = ?
                """,
                (JobStatus.EXPIRED.value, _now(), job_id),
            )
            connection.execute("DELETE FROM variations WHERE job_id = ?", (job_id,))

    async def mark_expired(self, job_id: str) -> None:
        await asyncio.to_thread(self._mark_expired_sync, job_id)

    # --- Uso e reconciliação ---------------------------------------------

    def _count_jobs_by_status_sync(
        self, api_key_hash: str | None
    ) -> dict[str, int]:
        with self._connect() as connection:
            if api_key_hash is None:
                rows = connection.execute(
                    "SELECT status, COUNT(*) AS total FROM jobs GROUP BY status"
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT status, COUNT(*) AS total
                      FROM jobs
                     WHERE api_key_hash = ?
                     GROUP BY status
                    """,
                    (api_key_hash,),
                ).fetchall()
        return {str(row["status"]): int(row["total"]) for row in rows}

    async def count_jobs_by_status(
        self, api_key_hash: str | None = None
    ) -> dict[str, int]:
        """Conta jobs por status, no serviço inteiro ou de uma chave só."""
        return await asyncio.to_thread(
            self._count_jobs_by_status_sync, api_key_hash
        )

    def _bytes_used_by_key_sync(self, api_key_hash: str) -> int:
        """Bytes contabilizados no banco para uma chave.

        São duas parcelas: as saídas já gravadas (todas as variações de jobs
        que ainda não expiraram) e as entradas que continuam em disco (só
        jobs que ainda não terminaram — depois disso o upload é apagado).
        """
        with self._connect() as connection:
            saidas = connection.execute(
                """
                SELECT COALESCE(SUM(v.size_bytes), 0) AS total
                  FROM variations AS v
                  JOIN jobs AS j ON j.job_id = v.job_id
                 WHERE j.api_key_hash = ? AND j.status != ?
                """,
                (api_key_hash, JobStatus.EXPIRED.value),
            ).fetchone()
            entradas = connection.execute(
                """
                SELECT COALESCE(SUM(input_bytes), 0) AS total
                  FROM jobs
                 WHERE api_key_hash = ? AND status IN (?, ?)
                """,
                (
                    api_key_hash,
                    JobStatus.PENDING.value,
                    JobStatus.RUNNING.value,
                ),
            ).fetchone()
        return int(saidas["total"]) + int(entradas["total"])

    async def bytes_used_by_key(self, api_key_hash: str) -> int:
        return await asyncio.to_thread(
            self._bytes_used_by_key_sync, api_key_hash
        )

    def _job_ids_with_expected_directory_sync(self) -> set[str]:
        """Jobs que legitimamente podem ter um diretório de saída em disco.

        Um job expirado já teve os arquivos apagados: se o diretório dele
        ainda existe, é lixo de uma remoção interrompida no meio.
        """
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT job_id FROM jobs WHERE status != ?",
                (JobStatus.EXPIRED.value,),
            ).fetchall()
        return {str(row["job_id"]) for row in rows}

    async def job_ids_with_expected_directory(self) -> set[str]:
        return await asyncio.to_thread(
            self._job_ids_with_expected_directory_sync
        )

    def _list_completed_jobs_sync(self) -> list[dict[str, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT job_id, output_dir FROM jobs WHERE status = ?",
                (JobStatus.COMPLETED.value,),
            ).fetchall()
        return [dict(row) for row in rows]

    async def list_completed_jobs(self) -> list[dict[str, str]]:
        """Jobs concluídos, que obrigatoriamente deveriam ter diretório."""
        return await asyncio.to_thread(self._list_completed_jobs_sync)

    def _active_input_paths_sync(self) -> set[str]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT input_path FROM jobs WHERE status IN (?, ?)",
                (JobStatus.PENDING.value, JobStatus.RUNNING.value),
            ).fetchall()
        return {str(row["input_path"]) for row in rows}

    async def active_input_paths(self) -> set[str]:
        """Uploads que ainda pertencem a um job não terminado."""
        return await asyncio.to_thread(self._active_input_paths_sync)

    # --- Rate limiting ---------------------------------------------------

    def _count_and_record_event_sync(
        self, api_key_hash: str, event_type: str, window_seconds: int, limit: int
    ) -> bool:
        """Conta eventos na janela e registra o novo se houver espaço.

        A contagem e a inserção acontecem na mesma transação para que duas
        requisições simultâneas não passem juntas pelo limite.
        """
        cutoff = (
            datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
        ).isoformat()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM rate_limit_events WHERE created_at < ?",
                (
                    (
                        datetime.now(timezone.utc) - timedelta(days=1)
                    ).isoformat(),
                ),
            )
            row = connection.execute(
                """
                SELECT COUNT(*) AS total
                  FROM rate_limit_events
                 WHERE api_key_hash = ? AND event_type = ? AND created_at >= ?
                """,
                (api_key_hash, event_type, cutoff),
            ).fetchone()
            if int(row["total"]) >= limit:
                return False
            connection.execute(
                """
                INSERT INTO rate_limit_events (api_key_hash, event_type, created_at)
                VALUES (?, ?, ?)
                """,
                (api_key_hash, event_type, _now()),
            )
            return True

    async def count_and_record_event(
        self, *, api_key_hash: str, event_type: str, window_seconds: int, limit: int
    ) -> bool:
        """Registra o evento se ainda houver espaço na janela. Devolve se passou."""
        return await asyncio.to_thread(
            self._count_and_record_event_sync,
            api_key_hash,
            event_type,
            window_seconds,
            limit,
        )
