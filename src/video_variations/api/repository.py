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

SCHEMA_VERSION = 1

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
        input_path      TEXT NOT NULL,
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
        """Cria o schema e registra a versão. Idempotente."""
        with self._connect() as connection:
            for statement in SCHEMA_STATEMENTS:
                connection.execute(statement)
            row = connection.execute("SELECT version FROM schema_version").fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO schema_version (version) VALUES (?)",
                    (SCHEMA_VERSION,),
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
        output_dir: Path,
        variations: list[tuple[str, dict[str, Any]]],
    ) -> None:
        timestamp = _now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO jobs (
                    job_id, api_key_hash, status, num_variations,
                    input_path, output_dir, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    api_key_hash,
                    JobStatus.PENDING.value,
                    num_variations,
                    str(input_path),
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
        output_dir: Path,
        variations: list[tuple[str, dict[str, Any]]],
    ) -> None:
        await asyncio.to_thread(
            self._create_job_sync,
            job_id=job_id,
            api_key_hash=api_key_hash,
            num_variations=num_variations,
            input_path=input_path,
            output_dir=output_dir,
            variations=variations,
        )

    def _set_job_status_sync(
        self, job_id: str, status: JobStatus, error: str | None
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE jobs SET status = ?, error = ?, updated_at = ? WHERE job_id = ?",
                (status.value, error, _now(), job_id),
            )

    async def set_job_status(
        self, job_id: str, status: JobStatus, error: str | None = None
    ) -> None:
        await asyncio.to_thread(self._set_job_status_sync, job_id, status, error)

    def _set_variation_result_sync(
        self,
        job_id: str,
        variation_id: str,
        status: str,
        error: str | None,
        size_bytes: int | None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE variations
                   SET status = ?, error = ?, size_bytes = ?
                 WHERE job_id = ? AND variation_id = ?
                """,
                (status, error, size_bytes, job_id, variation_id),
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
    ) -> None:
        await asyncio.to_thread(
            self._set_variation_result_sync,
            job_id,
            variation_id,
            status,
            error,
            size_bytes,
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
                SELECT variation_id, status, params_json, error, size_bytes
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
            }
            for row in variation_rows
        ]
        return job

    async def get_job(self, job_id: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._get_job_sync, job_id)

    def _list_pending_variations_sync(self, job_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT variation_id, params_json
                  FROM variations
                 WHERE job_id = ? AND status IN ('pending', 'running')
                 ORDER BY variation_id
                """,
                (job_id,),
            ).fetchall()
        return [
            {"variation_id": row["variation_id"], "params": json.loads(row["params_json"])}
            for row in rows
        ]

    async def list_pending_variations(self, job_id: str) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._list_pending_variations_sync, job_id)

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
            rows = connection.execute(
                """
                SELECT job_id, input_path, output_dir
                  FROM jobs
                 WHERE status != ? AND updated_at < ?
                """,
                (JobStatus.EXPIRED.value, cutoff),
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

    # --- Rate limiting ---------------------------------------------------

    def _count_and_record_event_sync(
        self, api_key_hash: str, event_type: str, window_seconds: int, limit: int
    ) -> tuple[bool, int]:
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
            used = int(row["total"])
            if used >= limit:
                return False, used
            connection.execute(
                """
                INSERT INTO rate_limit_events (api_key_hash, event_type, created_at)
                VALUES (?, ?, ?)
                """,
                (api_key_hash, event_type, _now()),
            )
            return True, used + 1

    async def count_and_record_event(
        self, *, api_key_hash: str, event_type: str, window_seconds: int, limit: int
    ) -> tuple[bool, int]:
        return await asyncio.to_thread(
            self._count_and_record_event_sync,
            api_key_hash,
            event_type,
            window_seconds,
            limit,
        )
