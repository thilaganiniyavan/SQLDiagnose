# cli.py
# Command-line access to the diagnosis, repair and NL2SQL services (no API server needed).
#
#   python cli.py diagnose "SELECT nme FROM singer" --db concert_singer
#   python cli.py repair   "SELEC name FORM singer" --db concert_singer
#   python cli.py nl2sql   "How many singers are from France?" --db concert_singer
#   python cli.py diagnose "SELECT ..." --ddl schema.sql --dialect postgres --restrict salaries
#   python cli.py dbs

import argparse
import json
import sys
from pathlib import Path

from deployment.api.main import PROJECT_ROOT, load_config
from services.schema_registry import SchemaRegistry


def build_schema(args):
    registry = SchemaRegistry()
    policy = {"restricted_tables": args.restrict or [], "restricted_columns": args.restrict_column or []}
    if args.schema:
        return registry.resolve(json.loads(Path(args.schema).read_text()), None, policy)
    if args.ddl:
        from data_pipeline.schema_parser import parse_ddl
        return registry.resolve(parse_ddl(Path(args.ddl).read_text(), args.dialect), None, policy)
    if args.sqlite:
        from data_pipeline.schema_parser import parse_sqlite_file
        return registry.resolve(parse_sqlite_file(args.sqlite), None, policy)
    if args.db:
        try:
            return registry.resolve(None, args.db, policy)
        except KeyError:
            sys.exit(f"Unknown example database '{args.db}'. List them with `python cli.py dbs`.")
    return None


def build_service(use_model: bool):
    from services.diagnosis import DiagnosisService
    classifier = None
    if use_model:
        model_dir = Path(load_config()["api"]["model_dir"])
        model_dir = model_dir if model_dir.is_absolute() else PROJECT_ROOT / model_dir
        if (model_dir / "sqldiagnose_labels.json").exists():
            from models.classifier import SQLErrorClassifier
            classifier = SQLErrorClassifier.from_pretrained(str(model_dir))
        else:
            print(f"(no classifier at {model_dir}; using the analyzer only)", file=sys.stderr)
    return DiagnosisService(classifier)


def main():
    ap = argparse.ArgumentParser(description="SQLDiagnose command line")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("diagnose", "repair", "nl2sql"):
        p = sub.add_parser(name)
        p.add_argument("text", help="SQL query (diagnose/repair) or question (nl2sql)")
        p.add_argument("--db", help="bundled example database id")
        p.add_argument("--schema", help="schema JSON file")
        p.add_argument("--ddl", help="file with CREATE TABLE statements")
        p.add_argument("--dialect", default="sqlite", help="dialect of --ddl")
        p.add_argument("--sqlite", help="SQLite database file to read the schema from")
        p.add_argument("--restrict", action="append", help="restricted table (repeatable)")
        p.add_argument("--restrict-column", action="append", help="restricted table.column (repeatable)")
        p.add_argument("--no-model", action="store_true", help="skip the neural classifier")
        p.add_argument("--json", action="store_true", help="print raw JSON")
    sub.add_parser("dbs", help="list bundled example databases")
    args = ap.parse_args()

    if args.cmd == "dbs":
        print("\n".join(SchemaRegistry().names()))
        return

    schema = build_schema(args)
    service = build_service(not args.no_model and args.cmd == "diagnose")

    if args.cmd == "diagnose":
        d = service.diagnose(args.text, schema)
        if args.json:
            print(json.dumps(d.to_dict(), indent=2))
            return
        print(f"{d.error_class}  (decided by {d.decided_by})")
        for i in (d.analysis.issues if d.analysis else []):
            print(f"  - [{i.error_class}] {i.message}")
        if d.model:
            print(f"  model: {d.model.error_class} ({d.model.confidence:.0%})")
        for n in d.notes:
            print(f"  note: {n}")
    elif args.cmd == "repair":
        r = service.repair(args.text, schema)
        if args.json:
            print(json.dumps(r.to_dict(), indent=2))
            return
        print(("VERIFIED FIX" if r.success else f"NOT FULLY REPAIRED ({r.remaining_error})"))
        if r.repaired_query:
            print(f"  {r.repaired_query}")
        print("\n".join("  " + line for line in r.explanation.splitlines()))
    else:
        if schema is None:
            sys.exit("nl2sql needs a schema (--db, --schema, --ddl or --sqlite).")
        from models.generator import T5SQLGenerator
        from services.nl2sql import NL2SQLService
        cfg = load_config()["api"]
        res = NL2SQLService(T5SQLGenerator(cfg["generator"]), service).run(args.text, schema)
        if args.json:
            print(json.dumps(res, indent=2))
            return
        print(f"{res['status'].upper()}: {res['sql']}")
        for c in res["candidates"]:
            print(f"  #{c['rank']} [{c['error_class']}] {c['sql']}")


if __name__ == "__main__":
    main()
