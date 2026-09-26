import pytest

VALID = [
    "SELECT name FROM singer WHERE country = 'France'",
    'SELECT name FROM singer WHERE country = "France"',
    "SELECT country, count(*) FROM singer GROUP BY country HAVING count(*) > 1",
    "SELECT s.name FROM singer AS s JOIN singer_in_concert AS sc ON s.singer_id = sc.singer_id",
    "SELECT T1.name, count(*) FROM singer AS T1 JOIN singer_in_concert AS T2 ON T1.singer_id = T2.singer_id GROUP BY T1.singer_id",
    "SELECT name FROM singer WHERE age > (SELECT avg(age) FROM singer)",
    "SELECT name FROM singer WHERE age IS NULL",
    "SELECT count(*) FROM singer;",
    "WITH old AS (SELECT * FROM singer WHERE age > 60) SELECT name FROM old",
    "SELECT name FROM singer UNION SELECT concert_name FROM concert",
    "SELECT s.name FROM singer s, singer_in_concert c WHERE s.singer_id = c.singer_id",
    "SELECT name FROM singer WHERE age = '42'",
    "SELECT T1.name FROM singer AS T1 JOIN singer_in_concert AS T2 JOIN concert AS T3 "
    "ON T1.singer_id = T2.singer_id AND T2.concert_id = T3.concert_id",
]


@pytest.mark.parametrize("sql", VALID)
def test_valid_queries_pass(analyzer, schema, sql):
    res = analyzer.analyze(sql, schema)
    assert res.error_class == "CORRECT", res.issues


CASES = [
    ("SELEC name FROM singer", "SYNTAX_ERROR"),
    ("SELECT name FROM singer WHERE", "SYNTAX_ERROR"),
    ("SELECT name FROM singer WHERE name = 'abc", "SYNTAX_ERROR"),
    ("SELECT name, FROM singer", "SYNTAX_ERROR"),
    ("SELECT count(* FROM singer", "SYNTAX_ERROR"),
    ("SELECT name FROM singers", "UNKNOWN_TABLE"),
    ("SELECT nme FROM singer", "UNKNOWN_COLUMN"),
    ("SELECT T9.name FROM singer AS T1", "UNKNOWN_COLUMN"),
    ("SELECT name FROM singer JOIN stadium ON singer.age = stadium.capacity", "AMBIGUOUS_REFERENCE"),
    ("SELECT T1.name FROM singer AS T1 JOIN concert AS T1 ON T1.singer_id = T1.concert_id", "AMBIGUOUS_REFERENCE"),
    ("SELECT name FROM singer WHERE age = 'old'", "DATATYPE_MISMATCH"),
    ("SELECT name FROM singer WHERE name = 5", "DATATYPE_MISMATCH"),
    ("SELECT avg(name) FROM singer", "DATATYPE_MISMATCH"),
    ("SELECT name FROM singer WHERE age = NULL", "SEMANTIC_ERROR"),
    ("SELECT name FROM singer WHERE count(*) > 1", "SEMANTIC_ERROR"),
    ("SELECT name, count(*) FROM singer", "SEMANTIC_ERROR"),
    ("SELECT country, name FROM singer GROUP BY country", "SEMANTIC_ERROR"),
    ("SELECT name FROM singer ORDER BY 3", "SEMANTIC_ERROR"),
    ("SELECT name FROM singer UNION SELECT concert_name, year FROM concert", "SEMANTIC_ERROR"),
    ("SELECT name FROM singer WHERE singer_id IN (SELECT singer_id, concert_id FROM singer_in_concert)", "SEMANTIC_ERROR"),
    ("SELECT cnt(*) FROM singer", "SEMANTIC_ERROR"),
    ("SELECT name FROM singer AS s JOIN concert AS c", "SEMANTIC_ERROR"),
    ("SELECT name FROM singer WHERE age = age", "SEMANTIC_ERROR"),
]


@pytest.mark.parametrize("sql,expected", CASES)
def test_error_classes(analyzer, schema, sql, expected):
    res = analyzer.analyze(sql, schema)
    assert res.error_class == expected, (res.error_class, [i.message for i in res.issues])
    assert res.issues and res.issues[0].error_class == expected


def test_priority_syntax_before_schema(analyzer, schema):
    # grammar errors are reported before name resolution, like a real engine
    assert analyzer.analyze("SELEC nme FROM singers", schema).error_class == "SYNTAX_ERROR"


def test_access_policy(analyzer, schema):
    s = schema.with_policy({"restricted_tables": ["stadium"], "restricted_columns": ["singer.age"]})
    assert analyzer.analyze("SELECT name FROM stadium", s).error_class == "PERMISSION_DENIED"
    assert analyzer.analyze("SELECT age FROM singer", s).error_class == "PERMISSION_DENIED"
    assert analyzer.analyze("SELECT * FROM singer", s).error_class == "PERMISSION_DENIED"
    assert analyzer.analyze("SELECT count(*) FROM singer", s).error_class == "CORRECT"
    assert analyzer.analyze("SELECT name FROM singer", s).error_class == "CORRECT"


def test_without_schema_checks_grammar_and_semantics(analyzer):
    assert analyzer.analyze("SELECT a FROM t WHERE b > 1").error_class == "CORRECT"
    assert analyzer.analyze("SELECT a FROM t WHRE b > 1").error_class == "SYNTAX_ERROR"
    assert analyzer.analyze("SELECT a FROM t WHERE b = NULL").error_class == "SEMANTIC_ERROR"
    assert analyzer.analyze("SELECT a FROM t WHERE sum(b) > 1").error_class == "SEMANTIC_ERROR"
    res = analyzer.analyze("SELECT a FROM t")
    assert res.schema_checked is False


@pytest.mark.parametrize("sql", ["", "   ", ";", "ATTACH DATABASE '/tmp/x.db' AS x", "PRAGMA table_info(singer)",
                                 "SELECT 1; DROP TABLE singer"])
def test_rejects_non_queries(analyzer, schema, sql):
    assert analyzer.analyze(sql, schema).error_class == "SYNTAX_ERROR"


def test_analyzer_never_touches_files(analyzer, schema, tmp_path):
    target = tmp_path / "evil.db"
    analyzer.analyze(f"ATTACH DATABASE '{target}' AS evil", schema)
    assert not target.exists()
