# workspace.py
# Per-client persistence for the web app: run history and saved schemas (SQLite, stdlib only).
#
# A "client" is an opaque id the browser generates once and sends with every request
# (X-Client-Id). There are no accounts; the id only keeps one browser's workspace apart
# from another's on a shared deployment.

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

HISTORY_LIMIT = 500            # entries kept per client (oldest are pruned)
MAX_RESULT_BYTES = 512 * 1024  # larger results are stored without their payload

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS history (
    id          TEXT PRIMARY KEY,
    client_id   TEXT NOT NULL,
    kind        TEXT NOT NULL,
    title       TEXT NOT NULL,
    context     TEXT NOT NULL,
    error_class TEXT,
    summary     TEXT NOT NULL,
    result      TEXT,
    created_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS history_client ON history (client_id, created_at DESC);

CREATE TABLE IF NOT EXISTS saved_schemas (
    id              TEXT PRIMARY KEY,
    client_id       TEXT NOT NULL,
    name            TEXT NOT NULL,
    source          TEXT NOT NULL,
    database_schema TEXT NOT NULL,
    access_policy   TEXT,
    database_file   TEXT,
    created_at      REAL NOT NULL,
    updated_at      REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS saved_schemas_client ON saved_schemas (client_id, updated_at DESC);
"""


class WorkspaceStore:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.uploads = self.directory / "uploads"
        self.uploads.mkdir(exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.directory / "workspace.db", check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(_SCHEMA_SQL)
            self._conn.commit()

    def close(self):
        with self._lock:
            self._conn.close()

    def _exec(self, sql: str, args=()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, args)
            self._conn.commit()
            return cur

    def _query(self, sql: str, args=()) -> List[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, args).fetchall()

    # ------------------------------------------------------------------ history
    def add_history(self, client_id: str, kind: str, title: str, context: Dict[str, Any],
                    error_class: Optional[str], summary: Dict[str, Any], result: Any = None) -> str:
        hid = uuid.uuid4().hex
        payload = json.dumps(result) if result is not None else None
        if payload is not None and len(payload) > MAX_RESULT_BYTES:
            payload = None
        self._exec("INSERT INTO history VALUES (?,?,?,?,?,?,?,?,?)",
                   (hid, client_id, kind, title[:4000], json.dumps(context), error_class,
                    json.dumps(summary), payload, time.time()))
        self._exec("DELETE FROM history WHERE client_id = ? AND id NOT IN "
                   "(SELECT id FROM history WHERE client_id = ? ORDER BY created_at DESC LIMIT ?)",
                   (client_id, client_id, HISTORY_LIMIT))
        return hid

    @staticmethod
    def _history_row(row: sqlite3.Row, with_result: bool) -> Dict[str, Any]:
        item = {"id": row["id"], "kind": row["kind"], "title": row["title"], "context": json.loads(row["context"]),
                "error_class": row["error_class"], "summary": json.loads(row["summary"]),
                "created_at": row["created_at"], "has_result": row["result"] is not None}
        if with_result:
            item["result"] = json.loads(row["result"]) if row["result"] else None
        return item

    def list_history(self, client_id: str, kind: Optional[str] = None, search: Optional[str] = None,
                     limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        where, args = ["client_id = ?"], [client_id]
        if kind:
            where.append("kind = ?")
            args.append(kind)
        if search:
            where.append("(title LIKE ? ESCAPE '\\' OR error_class LIKE ? ESCAPE '\\')")
            pattern = "%" + search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            args += [pattern, pattern]
        clause = " AND ".join(where)
        total = self._query(f"SELECT COUNT(*) FROM history WHERE {clause}", args)[0][0]
        rows = self._query(f"SELECT * FROM history WHERE {clause} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                           args + [limit, offset])
        return {"total": total, "items": [self._history_row(r, False) for r in rows]}

    def get_history(self, client_id: str, hid: str) -> Optional[Dict[str, Any]]:
        rows = self._query("SELECT * FROM history WHERE client_id = ? AND id = ?", (client_id, hid))
        return self._history_row(rows[0], True) if rows else None

    def delete_history(self, client_id: str, hid: str) -> bool:
        return self._exec("DELETE FROM history WHERE client_id = ? AND id = ?", (client_id, hid)).rowcount > 0

    def clear_history(self, client_id: str) -> int:
        return self._exec("DELETE FROM history WHERE client_id = ?", (client_id,)).rowcount

    # ------------------------------------------------------------------ saved schemas
    @staticmethod
    def _schema_row(row: sqlite3.Row, with_schema: bool = True) -> Dict[str, Any]:
        schema = json.loads(row["database_schema"])
        item = {"id": row["id"], "name": row["name"], "source": row["source"],
                "access_policy": json.loads(row["access_policy"]) if row["access_policy"] else None,
                "executable": bool(row["database_file"]),
                "tables": len(schema), "columns": sum(len(t.get("columns", {})) for t in schema.values()),
                "created_at": row["created_at"], "updated_at": row["updated_at"]}
        if with_schema:
            item["database_schema"] = schema
        return item

    def create_schema(self, client_id: str, name: str, source: str, database_schema: Dict[str, Any],
                      access_policy: Optional[Dict[str, Any]] = None,
                      database_bytes: Optional[bytes] = None) -> Dict[str, Any]:
        sid = uuid.uuid4().hex
        db_file = None
        if database_bytes is not None:
            db_file = f"{sid}.sqlite"
            (self.uploads / db_file).write_bytes(database_bytes)
        now = time.time()
        self._exec("INSERT INTO saved_schemas VALUES (?,?,?,?,?,?,?,?,?)",
                   (sid, client_id, name, source, json.dumps(database_schema),
                    json.dumps(access_policy) if access_policy else None, db_file, now, now))
        return self.get_schema(client_id, sid)

    def list_schemas(self, client_id: str) -> List[Dict[str, Any]]:
        rows = self._query("SELECT * FROM saved_schemas WHERE client_id = ? ORDER BY updated_at DESC", (client_id,))
        return [self._schema_row(r, with_schema=False) for r in rows]

    def get_schema(self, client_id: str, sid: str) -> Optional[Dict[str, Any]]:
        rows = self._query("SELECT * FROM saved_schemas WHERE client_id = ? AND id = ?", (client_id, sid))
        return self._schema_row(rows[0]) if rows else None

    def update_schema(self, client_id: str, sid: str, name: Optional[str] = None,
                      database_schema: Optional[Dict[str, Any]] = None,
                      access_policy: Optional[Dict[str, Any]] = None,
                      clear_policy: bool = False) -> Optional[Dict[str, Any]]:
        sets, args = ["updated_at = ?"], [time.time()]
        if name is not None:
            sets.append("name = ?")
            args.append(name)
        if database_schema is not None:
            sets.append("database_schema = ?")
            args.append(json.dumps(database_schema))
        if access_policy is not None or clear_policy:
            sets.append("access_policy = ?")
            args.append(json.dumps(access_policy) if access_policy else None)
        cur = self._exec(f"UPDATE saved_schemas SET {', '.join(sets)} WHERE client_id = ? AND id = ?",
                         args + [client_id, sid])
        return self.get_schema(client_id, sid) if cur.rowcount else None

    def delete_schema(self, client_id: str, sid: str) -> bool:
        rows = self._query("SELECT database_file FROM saved_schemas WHERE client_id = ? AND id = ?", (client_id, sid))
        if not rows:
            return False
        self._exec("DELETE FROM saved_schemas WHERE client_id = ? AND id = ?", (client_id, sid))
        if rows[0]["database_file"]:
            (self.uploads / rows[0]["database_file"]).unlink(missing_ok=True)
        return True

    def database_path(self, client_id: str, sid: str) -> Optional[Path]:
        rows = self._query("SELECT database_file FROM saved_schemas WHERE client_id = ? AND id = ?", (client_id, sid))
        if not rows or not rows[0]["database_file"]:
            return None
        path = self.uploads / rows[0]["database_file"]
        return path if path.exists() else None
