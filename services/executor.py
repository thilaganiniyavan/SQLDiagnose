# executor.py
# Runs a query against a real SQLite database, strictly read-only and time-limited, so the
# UI can show what a (repaired or generated) query actually returns.

import base64
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List

# Authorizer actions a read-only SELECT may need. Everything else (writes, ATTACH, PRAGMA, ...)
# is denied before the statement runs.
_ALLOWED_ACTIONS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}
if hasattr(sqlite3, "SQLITE_RECURSIVE"):
    _ALLOWED_ACTIONS.add(sqlite3.SQLITE_RECURSIVE)


class ExecutionError(Exception):
    """The query could not be run (SQLite error, not read-only, or too slow)."""


def _cell(value: Any) -> Any:
    if isinstance(value, bytes):
        return f"<blob {len(value)} bytes: {base64.b16encode(value[:16]).decode().lower()}{'…' if len(value) > 16 else ''}>"
    if isinstance(value, float) and value != value:          # NaN is not valid JSON
        return None
    return value


def execute_readonly(db_path: Path, query: str, max_rows: int = 200, timeout_s: float = 5.0) -> Dict[str, Any]:
    sql = query.strip().rstrip(";").strip()
    if not sql:
        raise ExecutionError("Empty query.")
    conn = sqlite3.connect(f"file:{Path(db_path).resolve()}?mode=ro", uri=True, check_same_thread=False)
    try:
        conn.set_authorizer(lambda action, *_: sqlite3.SQLITE_OK if action in _ALLOWED_ACTIONS else sqlite3.SQLITE_DENY)
        deadline = time.monotonic() + timeout_s
        conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10_000)
        # Spider databases contain some text that is not valid UTF-8
        conn.text_factory = lambda b: b.decode("utf-8", errors="replace")
        start = time.perf_counter()
        try:
            cur = conn.execute(sql)
            rows: List[tuple] = cur.fetchmany(max_rows + 1)
        except sqlite3.DatabaseError as e:
            msg = str(e)
            if msg == "interrupted":
                msg = f"The query took longer than {timeout_s:g} s and was stopped."
            elif "not authorized" in msg:
                msg = "Only read-only SELECT queries can be run."
            elif "one statement at a time" in msg:
                msg = "Run one statement at a time."
            raise ExecutionError(msg) from None
        except sqlite3.Warning as e:
            raise ExecutionError(str(e)) from None
        if cur.description is None:
            raise ExecutionError("The statement returned no result set.")
        elapsed = (time.perf_counter() - start) * 1000
        truncated = len(rows) > max_rows
        rows = rows[:max_rows]
        return {"columns": [d[0] for d in cur.description],
                "rows": [[_cell(v) for v in r] for r in rows],
                "row_count": len(rows), "truncated": truncated, "elapsed_ms": round(elapsed, 2)}
    finally:
        conn.close()
