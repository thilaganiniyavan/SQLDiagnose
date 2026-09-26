# evaluate.py
# End-to-end evaluation. Writes reports/evaluation_report.md, reports/results.json and figures.
#
#   python -m evaluation.evaluate --model-dir models/checkpoints/codeberta-small/best
#   python -m evaluation.evaluate --model-dir A/best --model-dir B/best     # compare several checkpoints
#   python -m evaluation.evaluate ... --nl2sql-samples 0                    # skip the (slow) NL2SQL study
#
# Sections
#   1. Classifier on the database-disjoint test split (+ TF-IDF baseline, no-schema ablation,
#      bootstrap CIs, McNemar test, calibration, per-operator accuracy, latency).
#   2. Analyzer audit on human-written Spider gold queries and on the access-policy set.
#   3. Repair: verified-fix rate and structural exact recovery of the original query.
#   4. NL2SQL: validity and execution accuracy of raw generation vs. verify/select/repair.
#   5. Token attribution examples.

import argparse
import json
import random
import re
import sqlite3
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import sqlglot
from sqlglot import exp

from analysis.analyzer import SQLAnalyzer
from analysis.schema import DatabaseSchema
from models.domain.labels import MODEL_CLASSES
from repair.repair_engine import SQLRepairEngine
from .baselines import TfidfBaseline
from .metrics import (bootstrap_ci, classification_metrics, mcnemar_exact, plot_confusion, plot_grouped_bars,
                      plot_reliability, plot_training_curve)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data" / "processed"
SPIDER_ROOT = PROJECT_ROOT / "data" / "raw" / "spider_data"


def load_jsonl(path: Path) -> List[Dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f]


def pct(x: Optional[float]) -> str:
    return "–" if x is None else f"{100 * x:.1f}"


# ---------------------------------------------------------------------- 1. classifier
def evaluate_classifier(clf, rows, schemas, name: str, fig_dir: Path, with_schema: bool = True) -> Dict:
    labels = clf.labels
    y = [labels.index(r["label"]) for r in rows]
    sch = [schemas[r["db_id"]] if with_schema else None for r in rows]
    t = time.perf_counter()
    probs = np.array(clf.predict_proba([r["sql"] for r in rows], sch, batch_size=32))
    elapsed = time.perf_counter() - t
    pred = probs.argmax(1).tolist()
    m = classification_metrics(y, pred, labels, probs)
    m["ci95"] = bootstrap_ci(y, pred, len(labels))
    m["throughput_qps"] = len(rows) / elapsed
    by_op = defaultdict(lambda: [0, 0])
    for r, p in zip(rows, pred):
        by_op[(r["label"], r["mutation"])][0] += int(labels[p] == r["label"])
        by_op[(r["label"], r["mutation"])][1] += 1
    m["per_operator"] = {f"{c}/{o}": {"accuracy": a / n, "n": n} for (c, o), (a, n) in sorted(by_op.items())}
    m["correct"] = [labels[p] == r["label"] for r, p in zip(rows, pred)]
    m["probs"] = probs
    return m


def single_query_latency(clf, rows, schemas, n: int = 60) -> Dict[str, float]:
    sample = rows[:n]
    times = []
    for r in sample:
        t = time.perf_counter()
        clf.predict(r["sql"], schemas[r["db_id"]])
        times.append((time.perf_counter() - t) * 1000)
    return {"mean_ms": statistics.mean(times), "p95_ms": float(np.percentile(times, 95))}


def evaluate_baseline(train, test, schemas) -> Dict:
    from models.classifier import schema_text
    labels = MODEL_CLASSES
    base = TfidfBaseline().fit([r["sql"] for r in train], [schema_text(r["sql"], schemas[r["db_id"]]) for r in train],
                               [labels.index(r["label"]) for r in train])
    probs = base.predict_proba([r["sql"] for r in test], [schema_text(r["sql"], schemas[r["db_id"]]) for r in test])
    y = [labels.index(r["label"]) for r in test]
    pred = probs.argmax(1).tolist()
    m = classification_metrics(y, pred, labels, probs)
    m["ci95"] = bootstrap_ci(y, pred, len(labels))
    m["correct"] = [p == t for p, t in zip(pred, y)]
    m["train_seconds"] = base.train_seconds
    return m


# ---------------------------------------------------------------------- 2. analyzer audits
def audit_gold_queries(analyzer: SQLAnalyzer) -> Optional[Dict]:
    if not (SPIDER_ROOT / "tables.json").exists():
        return None
    from data_pipeline.spider import SpiderCorpus
    corpus = SpiderCorpus(SPIDER_ROOT)
    counts, examples = Counter(), defaultdict(list)
    total = 0
    for split in ("train", "dev"):
        for ex in corpus.examples(split):
            total += 1
            res = analyzer.analyze(ex["query"], corpus.schema(ex["db_id"]))
            counts[res.error_class] += 1
            if res.is_error and len(examples[res.error_class]) < 3 \
                    and all(e["sql"] != ex["query"] for e in examples[res.error_class]):
                examples[res.error_class].append({"db_id": ex["db_id"], "sql": ex["query"],
                                                  "issue": res.issues[0].message})
    return {"total": total, "pass_rate": counts["CORRECT"] / total, "counts": dict(counts), "examples": dict(examples)}


def evaluate_permissions(analyzer: SQLAnalyzer, rows, schemas) -> Dict:
    correct = 0
    for r in rows:
        schema = schemas[r["db_id"]].with_policy(r["access_policy"])
        got = analyzer.analyze(r["sql"], schema).error_class
        correct += int((got == "PERMISSION_DENIED") == (r["label"] == "PERMISSION_DENIED"))
    return {"n": len(rows), "accuracy": correct / max(1, len(rows)),
            "violations": sum(r["label"] == "PERMISSION_DENIED" for r in rows)}


# ---------------------------------------------------------------------- 3. repair
def canonical(sql: str) -> str:
    """Structure-only form: table aliases renamed t1..tn, literals replaced by typed placeholders."""
    try:
        tree = sqlglot.parse_one(sql.strip().rstrip(";"), read="sqlite")
    except Exception:
        return re.sub(r"\s+", " ", sql.lower()).strip()
    mapping = {}
    for i, t in enumerate(tree.find_all(exp.Table), 1):
        if t.alias:
            mapping[t.alias.lower()] = f"t{i}"
            t.set("alias", exp.TableAlias(this=exp.to_identifier(f"t{i}")))
    for c in tree.find_all(exp.Column):
        if c.table and c.table.lower() in mapping:
            c.set("table", exp.to_identifier(mapping[c.table.lower()]))
    for lit in list(tree.find_all(exp.Literal)):
        lit.replace(exp.Literal.string("?") if lit.is_string else exp.Literal.number(0))
    return re.sub(r"\s+", " ", tree.sql(dialect="sqlite").lower()).strip()


def evaluate_repair(rows, schemas, engine: SQLRepairEngine) -> Dict:
    stats = defaultdict(Counter)
    times = []
    for r in rows:
        if r["label"] == "CORRECT":
            continue
        t = time.perf_counter()
        res = engine.repair(r["sql"], schemas[r["db_id"]])
        times.append((time.perf_counter() - t) * 1000)
        exact = res.success and canonical(res.repaired_query) == canonical(r["source_sql"])
        for key in (r["label"], "ALL", f"{r['label']}/{r['mutation']}"):
            stats[key]["n"] += 1
            stats[key]["verified"] += int(res.success)
            stats[key]["exact"] += int(exact)
            stats[key]["steps"] += len(res.steps)
    out = {k: {"n": v["n"], "verified_rate": v["verified"] / v["n"], "exact_rate": v["exact"] / v["n"]}
           for k, v in stats.items()}
    out["latency_ms"] = {"mean": statistics.mean(times), "p95": float(np.percentile(times, 95))} if times else {}
    return out


# ---------------------------------------------------------------------- 4. NL2SQL
def _execute(db_path: Path, sql: str, timeout_s: float = 5.0):
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.text_factory = lambda b: b.decode("utf-8", errors="replace")
    start = time.time()
    conn.set_progress_handler(lambda: int(time.time() - start > timeout_s), 10_000)
    try:
        return conn.execute(sql).fetchall()
    except Exception:
        return None
    finally:
        conn.close()


def _same_result(pred_sql: Optional[str], gold_sql: str, db_path: Path) -> bool:
    if not pred_sql:
        return False
    gold = _execute(db_path, gold_sql)
    pred = _execute(db_path, pred_sql)
    if gold is None or pred is None:
        return False
    if re.search(r"\border\s+by\b", gold_sql, re.I):
        return pred == gold
    return Counter(map(repr, pred)) == Counter(map(repr, gold))


def evaluate_nl2sql(service, n: int, seed: int = 0) -> Optional[Dict]:
    if n <= 0 or not (SPIDER_ROOT / "dev.json").exists():
        return None
    from data_pipeline.spider import SpiderCorpus
    corpus = SpiderCorpus(SPIDER_ROOT)
    examples = corpus.examples("dev")
    random.Random(seed).shuffle(examples)
    examples = examples[:n]
    agg = Counter()
    statuses = Counter()
    rows = []
    for i, ex in enumerate(examples):
        schema = corpus.schema(ex["db_id"])
        db = corpus.db_path(ex["db_id"])
        res = service.run(ex["question"], schema)
        cands = res["candidates"]
        raw = cands[0]["sql"] if cands else None
        raw_valid = bool(cands) and cands[0]["error_class"] == "CORRECT"
        selected = next((c["sql"] for c in cands if c["error_class"] == "CORRECT"), raw)
        selected_valid = any(c["error_class"] == "CORRECT" for c in cands)
        final_valid = res["status"] in ("valid", "valid_alternative", "repaired")
        agg["raw_valid"] += raw_valid
        agg["selected_valid"] += selected_valid
        agg["final_valid"] += final_valid
        agg["raw_exec"] += _same_result(raw, ex["query"], db)
        agg["selected_exec"] += _same_result(selected, ex["query"], db)
        agg["final_exec"] += _same_result(res["sql"], ex["query"], db)
        agg["time_ms"] += res["generation_time_ms"]
        statuses[res["status"]] += 1
        if cands and not raw_valid:
            rows.append({"question": ex["question"], "raw": raw, "raw_error": cands[0]["error_class"],
                         "final": res["sql"], "status": res["status"]})
        if (i + 1) % 25 == 0:
            print(f"  nl2sql {i + 1}/{len(examples)}", flush=True)
    k = len(examples)
    return {"n": k, "raw_validity": agg["raw_valid"] / k, "selected_validity": agg["selected_valid"] / k,
            "final_validity": agg["final_valid"] / k, "raw_execution_accuracy": agg["raw_exec"] / k,
            "selected_execution_accuracy": agg["selected_exec"] / k,
            "final_execution_accuracy": agg["final_exec"] / k, "mean_generation_ms": agg["time_ms"] / k,
            "status_counts": dict(statuses), "invalid_raw_examples": rows[:8]}


# ---------------------------------------------------------------------- 5. attributions
def attribution_examples(clf, rows, schemas, fig_dir: Path, k: int = 3) -> List[Dict]:
    from evaluation.explainability import plot_token_attributions
    out = []
    wanted = ["UNKNOWN_COLUMN", "SYNTAX_ERROR", "SEMANTIC_ERROR", "DATATYPE_MISMATCH"]
    for cls in wanted:
        if len(out) >= k:
            break
        cand = [r for r in rows if r["label"] == cls and len(r["sql"]) < 90]
        for r in cand[:10]:
            if clf.predict(r["sql"], schemas[r["db_id"]]).error_class != cls:
                continue
            e = clf.explain(r["sql"], schemas[r["db_id"]], method="ig", steps=24)
            name = f"xai_{cls.lower()}.png"
            plot_token_attributions(e["query_tokens"], f"{cls}: integrated gradients", fig_dir / name)
            top = sorted(e["query_tokens"], key=lambda t: -t["score"])[:3]
            out.append({"class": cls, "sql": r["sql"], "top_tokens": [t["token"] for t in top], "figure": name})
            break
    return out


# ---------------------------------------------------------------------- report
def write_report(res: Dict, out_dir: Path) -> None:
    L = ["# Evaluation Report", "",
         f"Generated by `python -m evaluation.evaluate` on {time.strftime('%Y-%m-%d %H:%M')}. "
         "All numbers below are produced by that command from the checked-in code and data.", ""]
    ds = res["dataset"]
    L += ["## Setup", "",
          f"- Test split: {ds['test']} queries from {ds['test_dbs']} Spider-dev databases that never appear in training "
          f"(train: {ds['train']} queries / {ds['train_dbs']} databases).",
          "- Labels: 7 learned classes (PERMISSION_DENIED is decided by the access-policy check and evaluated separately).",
          "- Every label is confirmed by the deterministic analyzer; the classifier is trained to reproduce those verdicts "
          "from the query text and a compact schema description.", ""]

    L += ["## 1. Classification (test split)", "",
          "| System | Accuracy | Macro-F1 | 95% CI (macro-F1) | Macro ROC-AUC | ECE | Throughput |",
          "|---|---|---|---|---|---|---|"]
    for name, m in res["classifiers"].items():
        ci = m["ci95"]["macro_f1"]
        qps = f"{m['throughput_qps']:.0f} q/s" if "throughput_qps" in m else "–"
        L.append(f"| {name} | {pct(m['accuracy'])} | {pct(m['macro_f1'])} | {pct(ci[0])}–{pct(ci[1])} | "
                 f"{pct(m.get('macro_roc_auc'))} | {m.get('ece', 0):.3f} | {qps} |")
    L.append("")
    if res.get("significance"):
        for k, v in res["significance"].items():
            L.append(f"- McNemar ({k}): {v['only_a']} test queries only the first system gets right, {v['only_b']} only "
                     f"the second; exact p = {v['p_value']:.2g}.")
        L.append("")
    main = res.get("main_model")
    if main:
        m = res["classifiers"][main]
        L += [f"### Per-class results — {main}", "", "| Class | Precision | Recall | F1 | Support |", "|---|---|---|---|---|"]
        for c, v in m["per_class"].items():
            L.append(f"| {c} | {pct(v['precision'])} | {pct(v['recall'])} | {pct(v['f1'])} | {v['support']} |")
        L += ["", f"![confusion matrix](figures/confusion_matrix.png)", "", "![per-class F1](figures/per_class_f1.png)", "",
              f"![reliability](figures/reliability.png)", ""]
        if res.get("latency"):
            lat = res["latency"]
            L.append(f"Single-query CPU latency of the classifier: mean {lat['mean_ms']:.0f} ms, p95 {lat['p95_ms']:.0f} ms. "
                     f"The analyzer takes {res['analyzer_latency_ms']:.1f} ms per query on average.")
            L.append("")
        weakest = sorted(m["per_operator"].items(), key=lambda kv: kv[1]["accuracy"])[:6]
        L += ["Hardest error-injection operators for the model:", "", "| Class / operator | Accuracy | n |", "|---|---|---|"]
        for k, v in weakest:
            L.append(f"| {k} | {pct(v['accuracy'])} | {v['n']} |")
        L.append("")
    if res.get("training_curve"):
        L += ["![training curve](figures/training_curve.png)", ""]

    audit = res.get("gold_audit")
    if audit:
        L += ["## 2. Analyzer audit", "",
              f"Human-written Spider gold queries (train + dev, {audit['total']}): **{pct(audit['pass_rate'])}%** pass the "
              "analyzer. The remaining ones are flagged for:", "", "| Verdict | Count |", "|---|---|"]
        for c, n in sorted(audit["counts"].items(), key=lambda kv: -kv[1]):
            L.append(f"| {c} | {n} |")
        L += ["", "Examples of flagged gold queries (these are genuine problems: non-portable GROUP BY usage, "
                  "type mismatches under the declared column types, missing join conditions):", ""]
        for c, exs in audit["examples"].items():
            for e in exs[:2]:
                L.append(f"- `{e['sql']}` — {e['issue']}")
        L.append("")
    if res.get("permissions"):
        p = res["permissions"]
        L += [f"Access-policy check: {pct(p['accuracy'])}% correct on {p['n']} query/policy pairs "
              f"({p['violations']} violations).", ""]

    rep = res.get("repair")
    if rep:
        L += ["## 3. Repair (test split, erroneous queries)", "",
              "*Verified* = the repaired query passes the analyzer. *Exact* = it is structurally identical to the original "
              "correct query (aliases and literal values normalised); for several error types exact recovery is impossible "
              "in principle (e.g. the intended value behind `age > 'young'`).", "",
              "| Class | n | Verified fix | Exact recovery |", "|---|---|---|---|"]
        for c in [c for c in MODEL_CLASSES if c != "CORRECT"] + ["ALL"]:
            if c in rep:
                v = rep[c]
                L.append(f"| {c} | {v['n']} | {pct(v['verified_rate'])} | {pct(v['exact_rate'])} |")
        if rep.get("latency_ms"):
            L.append(f"\nMean repair time {rep['latency_ms']['mean']:.0f} ms (p95 {rep['latency_ms']['p95']:.0f} ms).")
        L += ["", "![repair](figures/repair_by_class.png)", ""]

    nl = res.get("nl2sql")
    if nl:
        L += ["## 4. NL2SQL with verification and repair", "",
              f"{nl['n']} random Spider-dev questions, generator `{res.get('generator', '')}`. "
              "Validity = passes the analyzer; execution accuracy = same result set as the gold query on the real database.", "",
              "| Pipeline | Valid SQL | Execution accuracy |", "|---|---|---|",
              f"| Raw top-1 generation | {pct(nl['raw_validity'])} | {pct(nl['raw_execution_accuracy'])} |",
              f"| + verify & select among candidates | {pct(nl['selected_validity'])} | {pct(nl['selected_execution_accuracy'])} |",
              f"| + repair when no candidate is valid | {pct(nl['final_validity'])} | {pct(nl['final_execution_accuracy'])} |",
              "", f"Mean generation time {nl['mean_generation_ms']:.0f} ms per question (CPU).", "",
              "![nl2sql](figures/nl2sql_pipeline.png)", ""]
        if nl["invalid_raw_examples"]:
            L += ["Invalid raw generations and what the pipeline returned:", ""]
            for e in nl["invalid_raw_examples"][:5]:
                L.append(f"- *{e['question']}* — raw `{e['raw']}` ({e['raw_error']}) → {e['status']}: `{e['final']}`")
            L.append("")

    if res.get("attributions"):
        L += ["## 5. Token attributions", ""]
        for a in res["attributions"]:
            L += [f"- {a['class']}: `{a['sql']}` — most influential tokens: {', '.join(a['top_tokens'])}",
                  f"  ![{a['class']}](figures/{a['figure']})"]
        L.append("")
    L += ["## Limitations", "",
          "- Errors are injected synthetically into Spider queries; real user errors can be more varied. The NL2SQL "
          "section is a check on naturally occurring (model-generated) mistakes.",
          "- Ground-truth labels come from the analyzer, so the analyzer itself is validated separately (Section 2) "
          "rather than scored on its own labels.",
          "- The analyzer uses SQLite semantics plus portable rules; dialect-specific behaviour of other engines may differ.",
          "- A verified repair is a valid query, not necessarily the intended one: when the original intent is not recoverable "
          "from the schema (e.g. a column name with no similar counterpart) the engine may return a different valid query. "
          "The exact-recovery column measures how often the intended query is restored.", ""]
    (out_dir / "evaluation_report.md").write_text("\n".join(L))


def main():
    ap = argparse.ArgumentParser(description="Evaluate classifier(s), analyzer, repair and NL2SQL.")
    ap.add_argument("--model-dir", action="append", default=[], help="fine-tuned checkpoint (repeatable)")
    ap.add_argument("--data-dir", type=Path, default=DATA_DIR)
    ap.add_argument("--out", type=Path, default=PROJECT_ROOT / "reports")
    ap.add_argument("--nl2sql-samples", type=int, default=150)
    ap.add_argument("--generator", default="cssupport/t5-small-awesome-text-to-sql")
    ap.add_argument("--nl2sql-cache", type=Path, default=None,
                    help="reuse NL2SQL results from this JSON if it matches --nl2sql-samples/--generator, else write it")
    ap.add_argument("--only-nl2sql", action="store_true", help="run just the NL2SQL study (use with --nl2sql-cache)")
    ap.add_argument("--limit", type=int, default=0, help="subsample the test split (quick runs)")
    ap.add_argument("--threads", type=int, default=0)
    args = ap.parse_args()

    import torch
    if args.threads:
        torch.set_num_threads(args.threads)
    out, fig_dir = args.out, args.out / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    schemas = {k: DatabaseSchema.from_dict(v, k) for k, v in json.loads((args.data_dir / "schemas.json").read_text()).items()}
    train = load_jsonl(args.data_dir / "train.jsonl")
    test = load_jsonl(args.data_dir / "test.jsonl")
    if args.limit:
        random.Random(0).shuffle(test)
        test = test[:args.limit]
    perm = load_jsonl(args.data_dir / "permission_test.jsonl") if (args.data_dir / "permission_test.jsonl").exists() else []

    res: Dict = {"dataset": {"train": len(train), "test": len(test), "train_dbs": len({r["db_id"] for r in train}),
                             "test_dbs": len({r["db_id"] for r in test})}, "classifiers": {}}
    analyzer = SQLAnalyzer()

    if args.only_nl2sql:
        args.model_dir = []
    else:
        print("[1/5] TF-IDF baseline ...", flush=True)
        res["classifiers"]["TF-IDF + LogReg"] = evaluate_baseline(train, test, schemas)

    from models.classifier import SQLErrorClassifier
    main_clf = None
    for md in args.model_dir:
        md = Path(md)
        clf = SQLErrorClassifier.from_pretrained(str(md))
        meta = json.loads((md / "sqldiagnose_labels.json").read_text())
        name = meta.get("backbone", md.parent.name).split("/")[-1]
        print(f"[1/5] classifier {name} ...", flush=True)
        res["classifiers"][name] = evaluate_classifier(clf, test, schemas, name, fig_dir)
        res["classifiers"][f"{name} (no schema input)"] = evaluate_classifier(clf, test, schemas, name, fig_dir,
                                                                              with_schema=False)
        if main_clf is None:
            main_clf, res["main_model"] = clf, name
            res["latency"] = single_query_latency(clf, test, schemas)
            res["training_curve"] = plot_training_curve(md.parent / "train_log.csv", fig_dir / "training_curve.png")

    t = time.perf_counter()
    for r in test:
        analyzer.analyze(r["sql"], schemas[r["db_id"]])
    res["analyzer_latency_ms"] = (time.perf_counter() - t) * 1000 / len(test)

    if main_clf is not None:
        name = res["main_model"]
        m = res["classifiers"][name]
        base = res["classifiers"]["TF-IDF + LogReg"]
        noschema = res["classifiers"][f"{name} (no schema input)"]
        res["significance"] = {f"{name} vs TF-IDF": mcnemar_exact(m["correct"], base["correct"]),
                               f"{name} vs no-schema ablation": mcnemar_exact(m["correct"], noschema["correct"])}
        plot_confusion(m["confusion_matrix"], main_clf.labels, f"{name} — test confusion matrix",
                       fig_dir / "confusion_matrix.png")
        series = {n: [v["per_class"][c]["f1"] for c in main_clf.labels] for n, v in res["classifiers"].items()}
        plot_grouped_bars(main_clf.labels, series, "F1", "Per-class F1 on unseen databases", fig_dir / "per_class_f1.png")
        y = [main_clf.labels.index(r["label"]) for r in test]
        plot_reliability(y, m["probs"], f"{name} calibration (ECE {m['ece']:.3f})", fig_dir / "reliability.png")

    if not args.only_nl2sql:
        print("[2/5] analyzer audit ...", flush=True)
        res["gold_audit"] = audit_gold_queries(analyzer)
        if perm:
            res["permissions"] = evaluate_permissions(analyzer, perm, schemas)

        print("[3/5] repair ...", flush=True)
        res["repair"] = evaluate_repair(test, schemas, SQLRepairEngine(analyzer))
        classes = [c for c in MODEL_CLASSES if c != "CORRECT" and c in res["repair"]]
        plot_grouped_bars(classes, {"verified fix": [res["repair"][c]["verified_rate"] for c in classes],
                                    "exact recovery": [res["repair"][c]["exact_rate"] for c in classes]},
                          "rate", "Repair on the test split", fig_dir / "repair_by_class.png")

    if args.nl2sql_samples > 0:
        res["generator"] = args.generator
        cache = args.nl2sql_cache
        cached = json.loads(cache.read_text()) if cache and cache.exists() else None
        if cached and cached.get("n") == args.nl2sql_samples and cached.get("generator") == args.generator:
            print(f"[4/5] NL2SQL: reusing {cache}", flush=True)
            res["nl2sql"] = cached
        else:
            print(f"[4/5] NL2SQL on {args.nl2sql_samples} questions ...", flush=True)
            from models.generator import T5SQLGenerator
            from services.diagnosis import DiagnosisService
            from services.nl2sql import NL2SQLService
            service = NL2SQLService(T5SQLGenerator(args.generator), DiagnosisService(None, analyzer))
            res["nl2sql"] = evaluate_nl2sql(service, args.nl2sql_samples)
            if cache and res["nl2sql"]:
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_text(json.dumps({**res["nl2sql"], "generator": args.generator}, indent=1))
        if args.only_nl2sql:
            print(json.dumps({k: v for k, v in res["nl2sql"].items() if k != "invalid_raw_examples"}, indent=1))
            return
        nl = res["nl2sql"]
        if nl:
            plot_grouped_bars(["valid SQL", "execution accuracy"],
                              {"raw top-1": [nl["raw_validity"], nl["raw_execution_accuracy"]],
                               "+ verify & select": [nl["selected_validity"], nl["selected_execution_accuracy"]],
                               "+ repair": [nl["final_validity"], nl["final_execution_accuracy"]]},
                              "rate", "NL2SQL pipeline (Spider dev)", fig_dir / "nl2sql_pipeline.png")

    if main_clf is not None:
        print("[5/5] attributions ...", flush=True)
        res["attributions"] = attribution_examples(main_clf, test, schemas, fig_dir)

    write_report(res, out)
    for m in res["classifiers"].values():
        m.pop("probs", None)
        m.pop("correct", None)
    (out / "results.json").write_text(json.dumps(res, indent=1, default=float))
    print(f"Wrote {out / 'evaluation_report.md'} and {out / 'results.json'}")


if __name__ == "__main__":
    main()
