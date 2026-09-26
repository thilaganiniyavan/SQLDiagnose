# build_dataset.py
# Builds the SQL error classification dataset from Spider.
#
#   python -m data_pipeline.build_dataset [--download] [--train-per-class 1000] ...
#
# Pipeline
#   1. Correct pool: Spider gold queries that the analyzer confirms as CORRECT.
#   2. Errors: class-targeted mutations of pool queries (mutator.py); a candidate is kept only
#      if the analyzer independently assigns it the target class.
#   3. Label-independent surface augmentation (keyword case, spacing, semicolons, literal values,
#      alias names) for every class, so formatting carries no label signal.
#   4. Database-disjoint splits: train/validation from Spider-train databases (split by database),
#      test from Spider-dev databases (never seen in training).
#   5. A PERMISSION_DENIED evaluation set pairing test queries with access policies.

import argparse
import json
import math
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from analysis.analyzer import SQLAnalyzer
from analysis.schema import DatabaseSchema
from models.domain.labels import MODEL_CLASSES
from .mutator import SQLMutator, _rename_alias, augment_surface
from .spider import DEFAULT_ROOT, SpiderCorpus, download_spider
from .sql_text import NAME_TYPES, SQLText

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = PROJECT_ROOT / "data" / "processed"
ERROR_CLASSES = [c for c in MODEL_CLASSES if c != "CORRECT"]
_ALIAS_POOLS = [["a", "b", "c", "d", "e"], ["x", "y", "z", "w", "v"], ["t1", "t2", "t3", "t4", "t5"],
                ["s", "r", "p", "q", "u"], ["A", "B", "C", "D", "E"]]


def _key(sql: str) -> str:
    return re.sub(r"\s+", " ", sql.strip().rstrip(";").lower())


def perturb_literals(sql: str, rng: random.Random) -> str:
    """Replaces numeric literals with other plausible numbers (keeps integer/decimal form)."""
    st = SQLText.try_parse(sql)
    if st is None:
        return sql
    edits = []
    for t in st.tokens:
        if t.type == "NUMBER" and rng.random() < 0.5:
            prev = st.prev(t)
            if prev is not None and prev.type in ("LIMIT", "ORDER_BY", "COMMA"):
                continue                      # keep LIMIT n and positional references stable
            if "." in t.text:
                new = f"{rng.uniform(0.5, 1000):.{len(t.text.split('.')[-1]) or 1}f}"
            else:
                v = int(float(t.text)) if t.text.replace(".", "").isdigit() else 10
                new = str(max(0, v + rng.randint(-max(3, v // 3), max(3, v // 3))))
            edits.append(st.replace_token(t, new))
    return st.apply(edits) if edits else sql


def rename_aliases(sql: str, schema: DatabaseSchema, rng: random.Random) -> str:
    st = SQLText.try_parse(sql)
    if st is None:
        return sql
    aliases = []
    for _, alias in st.table_refs(schema):
        if alias is not None and alias.lower not in [a.lower() for a in aliases]:
            aliases.append(alias.text)
    if not aliases:
        return sql
    pool = rng.choice(_ALIAS_POOLS)
    if len(aliases) > len(pool):
        return sql
    used = {t.lower for t in st.tokens if t.type in NAME_TYPES}
    mapping = {}
    for old, new in zip(aliases, pool):
        if new.lower() in used and new.lower() != old.lower():
            return sql
        mapping[old] = new
    edits = []
    for old, new in mapping.items():
        edits.extend(_rename_alias(st, old, new))
    try:
        return st.apply(edits)
    except ValueError:
        return sql


def surface(sql: str, schema: DatabaseSchema, rng: random.Random) -> str:
    if rng.random() < 0.3:
        sql = perturb_literals(sql, rng)
    if rng.random() < 0.3:
        sql = rename_aliases(sql, schema, rng)
    return augment_surface(sql, rng)


class DatasetBuilder:
    def __init__(self, corpus: SpiderCorpus, seed: int = 42):
        self.corpus = corpus
        self.seed = seed
        self.analyzer = SQLAnalyzer()

    # ------------------------------------------------------------------ pools
    def correct_pool(self, examples: List[Dict]) -> List[Tuple[str, str]]:
        seen, pool = set(), []
        for ex in examples:
            db, sql = ex["db_id"], ex["query"].strip()
            k = (db, _key(sql))
            if k in seen:
                continue
            seen.add(k)
            if self.analyzer.analyze(sql, self.corpus.schema(db)).error_class == "CORRECT":
                pool.append((db, sql))
        return pool

    def _foreign_names(self, dbs: List[str]) -> Tuple[List[str], List[str]]:
        tables, cols = set(), set()
        for db in dbs:
            s = self.corpus.schema(db)
            tables.update(s.table_names)
            cols.update(s.all_column_names())
        return sorted(tables), sorted(cols)

    # ------------------------------------------------------------------ generation
    def generate_split(self, split: str, pool: List[Tuple[str, str]], per_class: int,
                       rng: random.Random, seen: set) -> List[Dict]:
        dbs = sorted({db for db, _ in pool})
        other_dbs = [d for d in self.corpus.db_ids() if d not in dbs]
        values = sorted({t.text for _, sql in pool for t in (SQLText.try_parse(sql) or SQLText("")).tokens
                         if t.type == "STRING" or (t.type == "IDENTIFIER" and sql[t.start] == '"')})
        mutator = SQLMutator(*self._foreign_names(other_dbs), string_values=values)
        rows: List[Dict] = []

        # CORRECT
        order = pool[:]
        rng.shuffle(order)
        uses = Counter()
        max_uses = max(1, math.ceil(per_class / max(1, len(order)))) + 1
        attempts = 0
        count = 0
        while count < per_class and attempts < per_class * 20:
            db, sql = order[attempts % len(order)]
            attempts += 1
            if uses[(db, sql)] >= max_uses:
                continue
            schema = self.corpus.schema(db)
            cand = surface(sql, schema, rng)
            if _key(cand) in seen or self.analyzer.analyze(cand, schema).error_class != "CORRECT":
                continue
            seen.add(_key(cand))
            uses[(db, sql)] += 1
            rows.append(self._row(split, db, cand, "CORRECT", sql, "none", "Unmodified gold query", []))
            count += 1

        # error classes
        for cls in ERROR_CLASSES:
            order = pool[:]
            rng.shuffle(order)
            uses = Counter()
            count = attempts = 0
            while count < per_class and attempts < per_class * 40:
                db, sql = order[attempts % len(order)]
                attempts += 1
                if uses[(db, sql)] >= max_uses:
                    continue
                schema = self.corpus.schema(db)
                res = mutator.mutate(sql, schema, cls, rng)
                if res is None:
                    continue
                mutated, name, desc = res
                cand = surface(mutated, schema, rng)
                if _key(cand) in seen:
                    continue
                analysis = self.analyzer.analyze(cand, schema)
                if analysis.error_class != cls:
                    continue
                seen.add(_key(cand))
                uses[(db, sql)] += 1
                rows.append(self._row(split, db, cand, cls, sql, name, desc, [i.message for i in analysis.issues]))
                count += 1
            if count < per_class:
                print(f"  [{split}] {cls}: only {count}/{per_class} verified samples could be generated")
        return rows

    @staticmethod
    def _row(split, db, sql, label, source, mutation, desc, issues) -> Dict:
        return {"split": split, "db_id": db, "sql": sql, "label": label, "source_sql": source,
                "mutation": mutation, "description": desc, "issues": issues}

    def permission_set(self, pool: List[Tuple[str, str]], n: int, rng: random.Random) -> List[Dict]:
        """Queries paired with access policies: half violate the policy, half do not."""
        rows = []
        order = pool[:]
        rng.shuffle(order)
        for db, sql in order:
            if len(rows) >= n:
                break
            schema = self.corpus.schema(db)
            st = SQLText.try_parse(sql)
            if st is None:
                continue
            used_tables = [t.text for t, _ in st.table_refs(schema)]
            if not used_tables:
                continue
            violate = len(rows) % 2 == 0
            if violate:
                if rng.random() < 0.5:
                    policy = {"restricted_tables": [rng.choice(used_tables)], "restricted_columns": []}
                else:
                    refs = st.column_refs(schema)
                    if not refs:
                        continue
                    _, col, table = rng.choice(refs)
                    policy = {"restricted_tables": [], "restricted_columns": [f"{table}.{col.text}"]}
                expected = "PERMISSION_DENIED"
            else:
                unused = [t for t in schema.table_names if t.lower() not in {u.lower() for u in used_tables}]
                if not unused:
                    continue
                policy = {"restricted_tables": [rng.choice(unused)], "restricted_columns": []}
                expected = "CORRECT"
            got = self.analyzer.analyze(sql, schema.with_policy(policy)).error_class
            if got != expected:
                continue
            rows.append({"db_id": db, "sql": sql, "access_policy": policy, "label": expected})
        return rows

    # ------------------------------------------------------------------ orchestration
    def build(self, train_per_class: int, val_per_class: int, test_per_class: int,
              val_db_fraction: float = 0.15) -> Dict[str, List[Dict]]:
        rng = random.Random(self.seed)
        train_examples = self.corpus.examples("train")
        dev_examples = self.corpus.examples("dev")

        train_dbs = sorted({e["db_id"] for e in train_examples})
        rng.shuffle(train_dbs)
        n_val = max(1, int(round(len(train_dbs) * val_db_fraction)))
        val_dbs = set(train_dbs[:n_val])

        print("Verifying gold queries with the analyzer ...")
        pool_train = self.correct_pool([e for e in train_examples if e["db_id"] not in val_dbs])
        pool_val = self.correct_pool([e for e in train_examples if e["db_id"] in val_dbs])
        pool_test = self.correct_pool(dev_examples)
        print(f"  correct pools: train={len(pool_train)} validation={len(pool_val)} test={len(pool_test)}")

        seen: set = set()
        splits = {}
        for name, pool, n in (("train", pool_train, train_per_class),
                              ("validation", pool_val, val_per_class),
                              ("test", pool_test, test_per_class)):
            print(f"Generating {name} ({n} per class) ...")
            rows = self.generate_split(name, pool, n, rng, seen)
            rng.shuffle(rows)
            splits[name] = rows
        splits["permission_test"] = self.permission_set(pool_test, 2 * test_per_class, rng)
        return splits


def export(splits: Dict[str, List[Dict]], corpus: SpiderCorpus, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    used_dbs = set()
    for name, rows in splits.items():
        for i, r in enumerate(rows):
            r.setdefault("id", f"{name}-{i:05d}")
            used_dbs.add(r["db_id"])
        with open(out_dir / f"{name}.jsonl", "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        if name != "permission_test":
            pd.DataFrame(rows).to_csv(out_dir / f"{name}.csv", index=False)
    schemas = {db: corpus.schema(db).to_dict() for db in sorted(used_dbs)}
    (out_dir / "schemas.json").write_text(json.dumps(schemas, indent=1))
    write_report(splits, out_dir / "dataset_report.md")


def write_report(splits: Dict[str, List[Dict]], path: Path) -> None:
    lines = ["# Dataset Report", "",
             "Generated by `python -m data_pipeline.build_dataset` from Spider 1.0.",
             "Every label is confirmed by the deterministic analyzer (`analysis/analyzer.py`).",
             "Train/validation use disjoint Spider-train databases; test uses the Spider-dev databases.", ""]
    lines += ["## Class distribution", "", "| Class | " + " | ".join(k for k in splits if k != "permission_test") + " |",
              "|---|" + "---|" * (len(splits) - 1)]
    classes = MODEL_CLASSES
    for c in classes:
        lines.append(f"| {c} | " + " | ".join(str(sum(r["label"] == c for r in rows))
                                             for k, rows in splits.items() if k != "permission_test") + " |")
    lines.append("| **Total** | " + " | ".join(str(len(rows)) for k, rows in splits.items() if k != "permission_test") + " |")
    for k in ("train", "validation", "test"):
        dbs = {r["db_id"] for r in splits[k]}
        lines.append(f"\n{k}: {len(dbs)} databases")
    perm = splits.get("permission_test", [])
    lines += ["", f"Permission evaluation set: {len(perm)} queries "
                  f"({sum(r['label'] == 'PERMISSION_DENIED' for r in perm)} violating an access policy).", ""]
    lines += ["## Mutation operators (train)", "", "| Class | Operator | Count |", "|---|---|---|"]
    mc = Counter((r["label"], r["mutation"]) for r in splits["train"])
    for (c, m), n in sorted(mc.items()):
        lines.append(f"| {c} | {m} | {n} |")
    lines += ["", "## Examples (test)", ""]
    rng = random.Random(0)
    for c in classes:
        rows = [r for r in splits["test"] if r["label"] == c]
        for r in rng.sample(rows, min(2, len(rows))):
            lines.append(f"- **{c}** ({r['mutation']}): `{r['sql']}`")
            if r["label"] != "CORRECT":
                lines.append(f"  - from: `{r['source_sql']}`")
    path.write_text("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--download", action="store_true", help="download Spider if missing")
    ap.add_argument("--download-only", action="store_true", help="only fetch Spider (e.g. for the evaluation audits)")
    ap.add_argument("--spider-root", type=Path, default=DEFAULT_ROOT)
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    ap.add_argument("--train-per-class", type=int, default=1000)
    ap.add_argument("--val-per-class", type=int, default=150)
    ap.add_argument("--test-per-class", type=int, default=200)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    if args.download or args.download_only:
        download_spider(args.spider_root.parent)
        if args.download_only:
            return
    corpus = SpiderCorpus(args.spider_root)
    builder = DatasetBuilder(corpus, args.seed)
    splits = builder.build(args.train_per_class, args.val_per_class, args.test_per_class)
    export(splits, corpus, args.out)
    for k, v in splits.items():
        print(f"{k}: {len(v)} rows -> {args.out / (k + '.jsonl')}")


if __name__ == "__main__":
    main()
