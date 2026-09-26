# schema_parser.py
# Clean Architecture: Interface Adapter
# Extracts schemas (wire-format dicts, see analysis/schema.py) from SQLite files, DDL text,
# and live PostgreSQL / MySQL databases.

import logging
import os
import sqlite3
import tempfile
from typing import Any, Dict

import sqlglot

from analysis.schema import DatabaseSchema

logger = logging.getLogger("schema_parser")


def parse_sqlite_file(path: str) -> Dict[str, Any]:
    return DatabaseSchema.from_sqlite(path).to_dict()


def parse_sqlite_bytes(data: bytes) -> Dict[str, Any]:
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        return parse_sqlite_file(path)
    finally:
        os.unlink(path)


def parse_ddl(ddl: str, dialect: str = "sqlite") -> Dict[str, Any]:
    """
    Parses CREATE TABLE statements. Non-SQLite dialects are transpiled with sqlglot first; the
    statements are then executed in an empty in-memory SQLite database and introspected.
    """
    statements = sqlglot.transpile(ddl, read=dialect or "sqlite", write="sqlite")
    creates = [s for s in statements if s.strip().upper().startswith("CREATE TABLE")]
    if not creates:
        raise ValueError("No CREATE TABLE statements found.")
    conn = sqlite3.connect(":memory:")
    try:
        for stmt in creates:
            conn.execute(stmt)
        fd, path = tempfile.mkstemp(suffix=".sqlite")
        os.close(fd)
        try:
            disk = sqlite3.connect(path)
            conn.backup(disk)
            disk.close()
            schema = parse_sqlite_file(path)
        finally:
            os.unlink(path)
    finally:
        conn.close()
    # keep declared (dialect) types rather than SQLite's affinity names
    try:
        for stmt in sqlglot.parse(ddl, read=dialect or "sqlite"):
            if not isinstance(stmt, sqlglot.exp.Create) or not isinstance(stmt.this, sqlglot.exp.Schema):
                continue
            table = stmt.this.this.name
            for col in stmt.this.expressions:
                if isinstance(col, sqlglot.exp.ColumnDef) and col.args.get("kind") is not None:
                    for t_name, t_info in schema.items():
                        if t_name.lower() == table.lower():
                            for c_name in list(t_info["columns"]):
                                if c_name.lower() == col.name.lower():
                                    t_info["columns"][c_name] = col.args["kind"].sql(dialect=dialect or "sqlite")
    except sqlglot.errors.SqlglotError:
        pass
    return schema


def _information_schema(cursor, schema_filter: str) -> Dict[str, Any]:
    schema: Dict[str, Any] = {}
    cursor.execute("SELECT table_name FROM information_schema.tables "
                   f"WHERE table_schema = {schema_filter} AND table_type = 'BASE TABLE'")
    for (t,) in cursor.fetchall():
        schema[t] = {"columns": {}, "primary_keys": [], "foreign_keys": []}
    cursor.execute("SELECT table_name, column_name, data_type FROM information_schema.columns "
                   f"WHERE table_schema = {schema_filter} ORDER BY table_name, ordinal_position")
    for t, c, typ in cursor.fetchall():
        if t in schema:
            schema[t]["columns"][c] = str(typ).upper()
    return schema


def parse_postgresql(conn_string: str) -> Dict[str, Any]:
    """conn_string: libpq format, e.g. 'dbname=shop user=postgres password=... host=localhost'."""
    try:
        import psycopg2
    except ImportError as e:
        raise RuntimeError("PostgreSQL support needs `pip install psycopg2-binary`.") from e
    conn = psycopg2.connect(conn_string)
    try:
        cur = conn.cursor()
        schema = _information_schema(cur, "'public'")
        cur.execute("""
            SELECT kcu.table_name, kcu.column_name FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = 'public'""")
        for t, c in cur.fetchall():
            if t in schema:
                schema[t]["primary_keys"].append(c)
        cur.execute("""
            SELECT kcu.table_name, kcu.column_name, ccu.table_name, ccu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'""")
        for t, c, tt, tc in cur.fetchall():
            if t in schema:
                schema[t]["foreign_keys"].append({"column": c, "target_table": tt, "target_column": tc})
        return schema
    finally:
        conn.close()


def parse_mysql(params: Dict[str, Any]) -> Dict[str, Any]:
    """params: keyword arguments for pymysql.connect (host, user, password, database, port)."""
    try:
        import pymysql
    except ImportError as e:
        raise RuntimeError("MySQL support needs `pip install pymysql`.") from e
    conn = pymysql.connect(**params)
    try:
        cur = conn.cursor()
        schema = _information_schema(cur, "DATABASE()")
        cur.execute("SELECT table_name, column_name FROM information_schema.key_column_usage "
                    "WHERE constraint_name = 'PRIMARY' AND table_schema = DATABASE()")
        for t, c in cur.fetchall():
            if t in schema:
                schema[t]["primary_keys"].append(c)
        cur.execute("SELECT table_name, column_name, referenced_table_name, referenced_column_name "
                    "FROM information_schema.key_column_usage "
                    "WHERE referenced_table_name IS NOT NULL AND table_schema = DATABASE()")
        for t, c, tt, tc in cur.fetchall():
            if t in schema:
                schema[t]["foreign_keys"].append({"column": c, "target_table": tt, "target_column": tc})
        return schema
    finally:
        conn.close()
