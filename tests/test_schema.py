import sqlite3

import pytest

from analysis.schema import DatabaseSchema, normalize_type
from data_pipeline.schema_parser import parse_ddl, parse_sqlite_file


@pytest.mark.parametrize("raw,expected", [("INTEGER", "number"), ("varchar(20)", "text"), ("DECIMAL(10,2)", "number"),
                                          ("TIMESTAMP", "time"), ("bool", "boolean"), ("", "other"),
                                          ("number", "number"), ("BLOB", "other")])
def test_normalize_type(raw, expected):
    assert normalize_type(raw) == expected


def test_from_dict_accepts_all_column_formats():
    s = DatabaseSchema.from_dict({
        "a": {"columns": {"id": "INT"}},
        "b": {"columns": [{"name": "id", "type": "TEXT"}]},
        "c": {"columns": ["x", "y"]},
        "d": ["p", "q"],
    })
    assert s.column_type("a", "ID") == "number"
    assert s.column_type("b", "id") == "text"
    assert s.table("C").column_names == ["x", "y"]
    assert s.has_table("d")


def test_roundtrip_and_ddl(schema):
    again = DatabaseSchema.from_dict(schema.to_dict())
    assert again.to_dict() == schema.to_dict()
    ddl = schema.to_ddl()
    assert "CREATE TABLE concert" in ddl and "FOREIGN KEY (stadium_id) REFERENCES stadium(stadium_id)" in ddl


def test_serialize_for_model_puts_mentioned_tables_first(schema):
    text = schema.serialize_for_model("SELECT name FROM stadium")
    assert text.startswith("stadium: stadium_id num, name text, capacity num")
    assert "other tables:" in text and "singer" in text


def test_parse_ddl_postgres_dialect():
    s = parse_ddl("CREATE TABLE users (id SERIAL PRIMARY KEY, name VARCHAR(50));"
                  "CREATE TABLE orders (id INT PRIMARY KEY, user_id INT REFERENCES users(id));", "postgres")
    assert s["users"]["columns"] == {"id": "SERIAL", "name": "VARCHAR(50)"}
    assert s["orders"]["foreign_keys"] == [{"column": "user_id", "target_table": "users", "target_column": "id"}]


def test_parse_ddl_rejects_garbage():
    with pytest.raises(Exception):
        parse_ddl("this is not sql at all")


def test_parse_sqlite_file(tmp_path):
    path = tmp_path / "x.sqlite"
    conn = sqlite3.connect(path)
    conn.executescript("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT); "
                       "CREATE TABLE u (id INTEGER, t_id INTEGER REFERENCES t(id));")
    conn.close()
    s = parse_sqlite_file(str(path))
    assert s["t"]["primary_keys"] == ["id"]
    assert s["u"]["foreign_keys"][0]["target_table"] == "t"
