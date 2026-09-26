import pytest

from repair.repair_engine import SQLRepairEngine, words_to_number


@pytest.fixture(scope="module")
def engine(analyzer):
    return SQLRepairEngine(analyzer)


CASES = [
    ("SELEC name FROM singer", "SELECT name FROM singer"),
    ("SELECT name FORM singer", "SELECT name FROM singer"),
    ("SELECT name, FROM singer", "SELECT name FROM singer"),
    ("SELECT name FROM singer WHERE AND age > 3", "SELECT name FROM singer WHERE age > 3"),
    ("SELECT count(* FROM singer", "SELECT count(*) FROM singer"),
    ("SELECT country FROM singer GROUP country", "SELECT country FROM singer GROUP BY country"),
    ("SELECT name FROM singr", "SELECT name FROM singer"),
    ("SELECT nmae FROM singer", "SELECT name FROM singer"),
    ("SELECT name FROM singer WHERE name = 5", "SELECT name FROM singer WHERE name = '5'"),
    ("SELECT name FROM singer WHERE age > 'thirty'", "SELECT name FROM singer WHERE age > 30"),
    ("SELECT name FROM singer WHERE age = NULL", "SELECT name FROM singer WHERE age IS NULL"),
    ("SELECT name FROM singer WHERE age <> NULL", "SELECT name FROM singer WHERE NOT age IS NULL"),
    ("SELECT cnt(*) FROM singer", "SELECT count(*) FROM singer"),
    ("SELECT country, name, count(*) FROM singer GROUP BY country",
     "SELECT country, name, COUNT(*) FROM singer GROUP BY country, name"),
]


def _norm(s):
    return " ".join(s.lower().replace(";", "").split())


@pytest.mark.parametrize("bad,expected", CASES)
def test_repairs_are_verified(engine, analyzer, schema, bad, expected):
    res = engine.repair(bad, schema)
    assert res.success, res.explanation
    assert analyzer.analyze(res.repaired_query, schema).error_class == "CORRECT"
    assert _norm(res.repaired_query) == _norm(expected)


def test_ambiguous_column_gets_qualified(engine, analyzer, schema):
    res = engine.repair("SELECT name FROM singer AS s JOIN stadium AS t ON s.age = t.capacity", schema)
    assert res.success
    assert "s.name" in res.repaired_query or "t.name" in res.repaired_query


def test_missing_join_condition_uses_foreign_key(engine, schema):
    res = engine.repair("SELECT T2.name FROM concert AS T1 JOIN stadium AS T2 WHERE T1.year = 2014", schema)
    assert res.success, res.explanation
    assert "T1.stadium_id = T2.stadium_id" in res.repaired_query


def test_aggregate_in_where_becomes_subquery(engine, schema):
    res = engine.repair("SELECT name FROM singer WHERE age > avg(age)", schema)
    assert res.success
    assert "(SELECT AVG(age) FROM singer)" in res.repaired_query


def test_multiple_errors_fixed_in_sequence(engine, schema):
    res = engine.repair("SELECT nme, count(*) FROM singer WHERE age > 'thirty'", schema)
    assert res.success
    assert [s.error_class for s in res.steps] == ["UNKNOWN_COLUMN", "DATATYPE_MISMATCH", "SEMANTIC_ERROR"]
    assert _norm(res.repaired_query) == _norm("SELECT name, COUNT(*) FROM singer WHERE age > 30 GROUP BY name")


def test_correct_query_is_unchanged(engine, schema):
    res = engine.repair("SELECT name FROM singer", schema)
    assert res.success and not res.steps and res.repaired_query == "SELECT name FROM singer"


def test_permission_is_not_repaired(engine, schema):
    res = engine.repair("SELECT * FROM stadium", schema.with_policy({"restricted_tables": ["stadium"]}))
    assert not res.success and res.remaining_error == "PERMISSION_DENIED"


def test_unrepairable_is_reported_honestly(engine, schema):
    res = engine.repair("SELECT name FROM singer WHERE age = 'unknown'", schema)
    assert not res.success
    assert res.remaining_error == "DATATYPE_MISMATCH"


@pytest.mark.parametrize("text,value", [("thirty", 30), ("twenty five", 25), ("forty-two", 42),
                                        ("one hundred", 100), ("two thousand and ten", 2010), ("young", None)])
def test_words_to_number(text, value):
    assert words_to_number(text) == value


def test_five_errors_in_one_query(engine, schema):
    res = engine.repair("SELEC name, count(*) FORM singr WHERE age > 'thirty'", schema)
    assert res.success, res.explanation
    assert [s.error_class for s in res.steps] == ["SYNTAX_ERROR", "SYNTAX_ERROR", "UNKNOWN_TABLE",
                                                  "DATATYPE_MISMATCH", "SEMANTIC_ERROR"]
    assert _norm(res.repaired_query) == _norm("SELECT name, COUNT(*) FROM singer WHERE age > 30 GROUP BY name")


@pytest.mark.parametrize("typo_word,keyword", [("FORM", "FROM"), ("SELEC", "SELECT"), ("WHRE", "WHERE"),
                                               ("GROPU", "GROUP"), ("ODER", "ORDER")])
def test_keyword_typos_use_edit_distance(typo_word, keyword):
    from repair.repair_engine import keyword_matches
    assert keyword_matches(typo_word)[0] == keyword
