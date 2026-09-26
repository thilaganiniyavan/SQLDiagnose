import pytest

from services.diagnosis import DiagnosisService
from services.nl2sql import NL2SQLService


class ScriptedGenerator:
    """Returns pre-set candidates and records how it was called."""

    def __init__(self, first, more=()):
        self.first, self.more, self.calls = first, list(more), []

    def generate(self, question, schema, num_candidates=1):
        self.calls.append(num_candidates)
        pool = [self.first] if num_candidates == 1 else [self.first] + self.more
        return {"candidates": [{"sql": s, "confidence": 0.9} for s in pool][:num_candidates],
                "prompt_truncated": False, "inference_time_ms": 1.0, "model": "scripted"}


def test_valid_first_candidate_needs_one_generation(schema):
    gen = ScriptedGenerator("SELECT name FROM singer WHERE age > 30")
    res = NL2SQLService(gen, DiagnosisService(None)).run("singers over 30?", schema)
    assert res["status"] == "valid" and gen.calls == [1]


def test_invalid_first_candidate_triggers_alternatives(schema):
    gen = ScriptedGenerator("SELECT nme FROM singer", ["SELECT name FROM singer"])
    res = NL2SQLService(gen, DiagnosisService(None)).run("singer names?", schema)
    assert res["status"] == "valid_alternative" and res["sql"] == "SELECT name FROM singer"
    assert gen.calls == [1, 3]


def test_repair_when_no_candidate_is_valid(schema):
    gen = ScriptedGenerator("SELECT nmae FROM singr", ["SELECT nmae FROM singr"])
    res = NL2SQLService(gen, DiagnosisService(None)).run("singer names?", schema)
    assert res["status"] == "repaired" and res["sql"] == "SELECT name FROM singer"


@pytest.mark.parametrize("raw,expected", [
    ("SELECT name FROM singer;", "SELECT name FROM singer"),
    ("```sql\nSELECT name\nFROM singer\n```", "SELECT name FROM singer"),
    ("Here is the query:\n```\nSELECT 1;\n```\nIt returns one.", "SELECT 1"),
    ("SQL: SELECT a FROM t; SELECT b FROM t", "SELECT a FROM t"),
])
def test_extract_sql(raw, expected):
    pytest.importorskip("torch")          # extract_sql lives next to the torch-based generators
    from models.generator import extract_sql
    assert extract_sql(raw) == expected
