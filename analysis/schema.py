# schema.py
# Database schema model shared by the analyzer, the dataset builder, the
# classifier input formatter, the repair engine and the NL2SQL generator.

import re
import sqlite3
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

NUMBER, TEXT, TIME, BOOLEAN, OTHER = "number", "text", "time", "boolean", "other"

# Statements that could touch the file system are refused at compile time.
_DENIED_ACTIONS = {sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH, sqlite3.SQLITE_PRAGMA}


def _authorizer(action, *_):
    return sqlite3.SQLITE_DENY if action in _DENIED_ACTIONS else sqlite3.SQLITE_OK

_SQLITE_TYPE = {NUMBER: "NUMERIC", TEXT: "TEXT", TIME: "TEXT", BOOLEAN: "BOOLEAN", OTHER: ""}
_SHORT_TYPE = {NUMBER: "num", TEXT: "text", TIME: "time", BOOLEAN: "bool", OTHER: "any"}


def normalize_type(raw_type: Optional[str]) -> str:
    """Maps any engine-specific column type onto the five coarse types used for checks."""
    t = (raw_type or "").strip().lower()
    if not t:
        return OTHER
    if t in (NUMBER, TEXT, TIME, BOOLEAN, OTHER):
        return t
    if "bool" in t:
        return BOOLEAN
    if any(k in t for k in ("date", "time", "year")) and "int" not in t:
        return TIME
    if any(k in t for k in ("int", "real", "num", "dec", "float", "double", "money", "serial", "bit")):
        return NUMBER
    if any(k in t for k in ("char", "text", "clob", "string", "uuid", "json", "enum")):
        return TEXT
    return OTHER


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


@dataclass
class Column:
    name: str
    type: str = OTHER          # coarse type (see normalize_type)
    raw_type: str = ""


@dataclass
class Table:
    name: str
    columns: List[Column] = field(default_factory=list)
    primary_keys: List[str] = field(default_factory=list)
    foreign_keys: List[Tuple[str, str, str]] = field(default_factory=list)  # (column, target_table, target_column)

    def column(self, name: str) -> Optional[Column]:
        low = name.lower()
        for c in self.columns:
            if c.name.lower() == low:
                return c
        return None

    @property
    def column_names(self) -> List[str]:
        return [c.name for c in self.columns]


class DatabaseSchema:
    """
    In-memory description of a relational schema plus an optional access policy.

    Lookups are case-insensitive (as in SQLite, MySQL and unquoted PostgreSQL identifiers),
    while original spellings are kept for suggestions and DDL.
    """

    def __init__(
        self,
        tables: Iterable[Table],
        db_id: str = "user_schema",
        restricted_tables: Iterable[str] = (),
        restricted_columns: Iterable[str] = (),
    ):
        self.db_id = db_id
        self.tables: Dict[str, Table] = {t.name.lower(): t for t in tables}
        self.restricted_tables = {t.lower() for t in restricted_tables}
        self.restricted_columns = {c.lower() for c in restricted_columns}  # "table.column"
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ builders
    @classmethod
    def from_dict(cls, data: Dict[str, Any], db_id: str = "user_schema",
                  access_policy: Optional[Dict[str, Any]] = None) -> "DatabaseSchema":
        """
        Accepts the JSON wire format used by the API and the schema parsers:

            {"table": {"columns": {"col": "TYPE", ...} | [{"name": .., "type": ..}, ...] | ["col", ...],
                       "primary_keys": [...],
                       "foreign_keys": [{"column": .., "target_table": .., "target_column": ..}]}}
        """
        tables = []
        for tname, tinfo in (data or {}).items():
            if not isinstance(tinfo, dict):
                tinfo = {"columns": tinfo}
            raw_cols = tinfo.get("columns", {})
            cols: List[Column] = []
            if isinstance(raw_cols, dict):
                cols = [Column(c, normalize_type(t), str(t or "")) for c, t in raw_cols.items()]
            elif isinstance(raw_cols, list):
                for c in raw_cols:
                    if isinstance(c, dict):
                        cols.append(Column(c["name"], normalize_type(c.get("type")), str(c.get("type") or "")))
                    else:
                        cols.append(Column(str(c), OTHER, ""))
            fks = []
            for fk in tinfo.get("foreign_keys", []) or []:
                if isinstance(fk, dict):
                    fks.append((fk["column"], fk["target_table"], fk["target_column"]))
                else:
                    fks.append(tuple(fk))
            tables.append(Table(tname, cols, list(tinfo.get("primary_keys", []) or []), fks))
        policy = access_policy or {}
        return cls(tables, db_id,
                   policy.get("restricted_tables", []),
                   policy.get("restricted_columns", []))

    @classmethod
    def from_spider(cls, entry: Dict[str, Any]) -> "DatabaseSchema":
        """Builds a schema from one record of Spider's tables.json."""
        names = entry["table_names_original"]
        tables = [Table(n) for n in names]
        col_index: List[Tuple[int, str]] = []
        for (tidx, cname), ctype in zip(entry["column_names_original"], entry["column_types"]):
            col_index.append((tidx, cname))
            if tidx < 0:
                continue
            tables[tidx].columns.append(Column(cname, normalize_type(ctype), ctype))
        for pk in entry.get("primary_keys", []):
            for p in (pk if isinstance(pk, list) else [pk]):
                tidx, cname = col_index[p]
                tables[tidx].primary_keys.append(cname)
        for src, dst in entry.get("foreign_keys", []):
            stidx, scol = col_index[src]
            dtidx, dcol = col_index[dst]
            tables[stidx].foreign_keys.append((scol, names[dtidx], dcol))
        return cls(tables, entry["db_id"])

    @classmethod
    def from_sqlite(cls, db_path: str, db_id: Optional[str] = None) -> "DatabaseSchema":
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
            tables = []
            for (tname,) in cur.fetchall():
                t = Table(tname)
                for _, cname, ctype, _, _, pk in cur.execute(f"PRAGMA table_info({quote_ident(tname)})"):
                    t.columns.append(Column(cname, normalize_type(ctype), ctype or ""))
                    if pk:
                        t.primary_keys.append(cname)
                for row in cur.execute(f"PRAGMA foreign_key_list({quote_ident(tname)})"):
                    if row[3] and row[4]:
                        t.foreign_keys.append((row[3], row[2], row[4]))
                tables.append(t)
        finally:
            conn.close()
        return cls(tables, db_id or db_path)

    def with_policy(self, access_policy: Optional[Dict[str, Any]]) -> "DatabaseSchema":
        policy = access_policy or {}
        return DatabaseSchema(self.tables.values(), self.db_id,
                              policy.get("restricted_tables", []),
                              policy.get("restricted_columns", []))

    # ------------------------------------------------------------------ lookups
    def table(self, name: str) -> Optional[Table]:
        return self.tables.get(name.lower())

    def has_table(self, name: str) -> bool:
        return name.lower() in self.tables

    def column_type(self, table: str, column: str) -> Optional[str]:
        t = self.table(table)
        c = t.column(column) if t else None
        return c.type if c else None

    def tables_with_column(self, column: str) -> List[str]:
        return [t.name for t in self.tables.values() if t.column(column)]

    @property
    def table_names(self) -> List[str]:
        return [t.name for t in self.tables.values()]

    def all_column_names(self) -> List[str]:
        seen, out = set(), []
        for t in self.tables.values():
            for c in t.columns:
                if c.name.lower() not in seen:
                    seen.add(c.name.lower())
                    out.append(c.name)
        return out

    def is_restricted(self, table: str, column: Optional[str] = None) -> bool:
        if table.lower() in self.restricted_tables:
            return True
        return column is not None and f"{table.lower()}.{column.lower()}" in self.restricted_columns

    # ------------------------------------------------------------------ exports
    def to_dict(self) -> Dict[str, Any]:
        return {
            t.name: {
                "columns": {c.name: (c.raw_type or c.type) for c in t.columns},
                "primary_keys": list(t.primary_keys),
                "foreign_keys": [{"column": a, "target_table": b, "target_column": c} for a, b, c in t.foreign_keys],
            }
            for t in self.tables.values()
        }

    def access_policy(self) -> Dict[str, List[str]]:
        return {"restricted_tables": sorted(self.restricted_tables),
                "restricted_columns": sorted(self.restricted_columns)}

    def to_ddl(self) -> str:
        """Readable CREATE TABLE statements (used in the NL2SQL prompt and the UI)."""
        stmts = []
        for t in self.tables.values():
            parts = []
            for c in t.columns:
                col = f"{c.name} {c.raw_type or c.type}".strip()
                if c.name in t.primary_keys and len(t.primary_keys) == 1:
                    col += " PRIMARY KEY"
                parts.append(col)
            for col, tt, tc in t.foreign_keys:
                parts.append(f"FOREIGN KEY ({col}) REFERENCES {tt}({tc})")
            stmts.append(f"CREATE TABLE {t.name} (" + ", ".join(parts) + ");")
        return "\n".join(stmts)

    def _sqlite_ddl(self) -> str:
        stmts = []
        for t in self.tables.values():
            if t.name.lower().startswith("sqlite_"):
                continue                      # reserved names; SQLite provides these itself
            cols = ", ".join(f"{quote_ident(c.name)} {_SQLITE_TYPE[c.type]}".strip() for c in t.columns) or '"_dummy"'
            stmts.append(f"CREATE TABLE {quote_ident(t.name)} ({cols});")
        return "\n".join(stmts)

    def compile_errors(self, query: str) -> Optional[str]:
        """
        Compiles `query` with SQLite against an empty database that has this schema
        (EXPLAIN never executes the statement). Returns the compiler error or None.
        """
        with self._lock:
            if self._conn is None:
                conn = sqlite3.connect(":memory:", check_same_thread=False)
                conn.executescript(self._sqlite_ddl())
                conn.set_authorizer(_authorizer)
                self._conn = conn
            try:
                self._conn.execute("EXPLAIN " + query)
                return None
            except sqlite3.Warning as e:          # e.g. "You can only execute one statement at a time."
                return str(e)
            except sqlite3.Error as e:
                return str(e)

    def serialize_for_model(self, query: str) -> str:
        """
        Compact schema text appended to the query as the classifier's second segment:
        full column lists (with coarse types) for the tables the query mentions, then the
        names of the remaining tables. Keeps inputs short while retaining what is needed to
        judge table/column existence and types.
        """
        words = {w.lower() for w in _WORD_RE.findall(query or "")}
        mentioned = [t for t in self.tables.values() if t.name.lower() in words]
        parts = []
        for t in mentioned:
            cols = ", ".join(f"{c.name} {_SHORT_TYPE[c.type]}" for c in t.columns)
            parts.append(f"{t.name}: {cols}")
        others = [t.name for t in self.tables.values() if t not in mentioned]
        if others:
            parts.append("other tables: " + ", ".join(others))
        return " | ".join(parts)

def empty_schema() -> DatabaseSchema:
    return DatabaseSchema([], "empty")
