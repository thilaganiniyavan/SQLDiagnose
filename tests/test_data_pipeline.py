import json
import random
from collections import Counter

import pytest

from analysis.schema import DatabaseSchema
from data_pipeline.mutator import MUTATIONS, SQLMutator, augment_surface, toggle_plural, typo
from data_pipeline.sql_text import SQLText
from .conftest import DATA_DIR, needs_data

BASE = [
    "SELECT name, age FROM singer WHERE country = 'France' ORDER BY age DESC",
    "SELECT T1.name, count(*) FROM singer AS T1 JOIN singer_in_concert AS T2 ON T1.singer_id = T2.singer_id "
    "GROUP BY T1.singer_id HAVING count(*) > 1",
    "SELECT concert_name FROM concert WHERE year = 2014 AND stadium_id IN (SELECT stadium_id FROM stadium WHERE capacity > 500)",
    "SELECT name FROM singer WHERE age > (SELECT avg(age) FROM singer)",
]


def test_delete_token_keeps_words_apart():
    st = SQLText("SELECT a, FROM t")
    comma = st.of_type("COMMA")[0]
    assert st.apply([st.delete_token(comma)]) == "SELECT a FROM t"
    st = SQLText("SELECT x FROM t AS (T2 WHERE")
    paren = st.of_type("L_PAREN")[0]
    assert st.apply([st.delete_token(paren)]) == "SELECT x FROM t AS T2 WHERE"


def test_word_helpers():
    rng = random.Random(0)
    for w in ["singer", "concert", "name"]:
        assert typo(w, rng).lower() != w
    assert toggle_plural("singer") == "singers"
    assert toggle_plural("cities") == "city"


@pytest.mark.parametrize("cls", list(MUTATIONS))
def test_mutations_are_verified_by_analyzer(analyzer, schema, cls):
    """Across the base queries, each class must yield verified samples and nothing may crash."""
    mutator = SQLMutator(["employees", "flights"], ["salary", "dept_id"], ["Paris", "red"])
    rng = random.Random(1)
    verified = 0
    for sql in BASE * 5:
        res = mutator.mutate(sql, schema, cls, rng)
        if res is None:
            continue
        if analyzer.analyze(res[0], schema).error_class == cls:
            verified += 1
    assert verified > 0


def test_surface_augmentation_preserves_label(analyzer, schema):
    rng = random.Random(0)
    for sql in BASE:
        for _ in range(10):
            assert analyzer.analyze(augment_surface(sql, rng), schema).error_class == "CORRECT"


@needs_data
def test_processed_dataset_integrity(analyzer):
    schemas = {k: DatabaseSchema.from_dict(v, k) for k, v in json.loads((DATA_DIR / "schemas.json").read_text()).items()}
    splits = {}
    for name in ("train", "validation", "test"):
        with open(DATA_DIR / f"{name}.jsonl") as f:
            splits[name] = [json.loads(l) for l in f]
    # database-disjoint splits
    dbs = {k: {r["db_id"] for r in v} for k, v in splits.items()}
    assert not dbs["train"] & dbs["validation"]
    assert not dbs["train"] & dbs["test"]
    assert not dbs["validation"] & dbs["test"]
    # balanced classes
    for rows in splits.values():
        counts = Counter(r["label"] for r in rows)
        assert len(counts) == 7 and max(counts.values()) == min(counts.values())
    # no duplicate queries anywhere
    keys = [" ".join(r["sql"].lower().split()) for rows in splits.values() for r in rows]
    assert len(keys) == len(set(keys))
    # every label is what the analyzer says (sampled for speed)
    rows = [r for rows in splits.values() for r in rows]
    for r in random.Random(0).sample(rows, 1500):
        assert analyzer.analyze(r["sql"], schemas[r["db_id"]]).error_class == r["label"], r


@needs_data
def test_permission_set_matches_policies(analyzer):
    schemas = {k: DatabaseSchema.from_dict(v, k) for k, v in json.loads((DATA_DIR / "schemas.json").read_text()).items()}
    with open(DATA_DIR / "permission_test.jsonl") as f:
        rows = [json.loads(l) for l in f]
    assert rows
    for r in rows:
        got = analyzer.analyze(r["sql"], schemas[r["db_id"]].with_policy(r["access_policy"])).error_class
        assert got == r["label"]
