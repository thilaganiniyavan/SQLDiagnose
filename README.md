# SQLDiagnose

[![tests](https://github.com/thilaganiniyavan/SQLDiagnose/actions/workflows/tests.yml/badge.svg)](https://github.com/thilaganiniyavan/SQLDiagnose/actions/workflows/tests.yml)

Diagnose, explain and repair SQL queries, and turn natural-language questions into verified SQL.

Given a query and (optionally) a database schema, SQLDiagnose tells you **whether the query is wrong and why**,
using one of eight error classes, and **proposes a repaired query that it has verified**. A fine-tuned code
transformer gives a learned second opinion with token-level explanations, and a text-to-SQL model generates
queries that go through the same verify-and-repair loop.

| Class | Meaning | Example |
|---|---|---|
| `CORRECT` | no problem found | `SELECT name FROM singer WHERE age > 30` |
| `SYNTAX_ERROR` | grammar violation | `SELECT name FORM singer` |
| `UNKNOWN_TABLE` | table not in the schema | `SELECT name FROM singers` |
| `UNKNOWN_COLUMN` | column not in the referenced table | `SELECT nme FROM singer` |
| `DATATYPE_MISMATCH` | incompatible types compared / aggregated | `WHERE age = 'old'`, `AVG(name)` |
| `AMBIGUOUS_REFERENCE` | reference matches several tables, or an alias is reused | `SELECT name FROM singer JOIN stadium ON ...` |
| `PERMISSION_DENIED` | touches a table/column restricted by an access policy | `SELECT salary FROM staff` |
| `SEMANTIC_ERROR` | grammatical but logically invalid | `WHERE count(*) > 1`, `= NULL`, missing `GROUP BY` or join condition |

![Diagnosis and verified repair of a query with five errors](docs/images/diagnose.png)

<details><summary>More screenshots: join repair, NL→SQL, batch check, schemas, results, dark theme</summary>

![Missing join condition repaired from the foreign key](docs/images/join_repair.png)
![Question to verified SQL](docs/images/nl2sql.png)
![Batch check](docs/images/batch.png)
![Importing and browsing schemas](docs/images/schemas.png)
![Research results](docs/images/results.png)
![Dark theme](docs/images/dark.png)
</details>

## Results

Measured on 1,400 test queries from 20 Spider databases that never appear in training
(full report: [`reports/evaluation_report.md`](reports/evaluation_report.md), paper draft: [`reports/paper_draft.md`](reports/paper_draft.md)).

| | Accuracy | Macro-F1 |
|---|---|---|
| TF-IDF + logistic regression | 53.1 | 51.3 |
| CodeBERTa-small, query only (ablation) | 47.1 | 47.0 |
| **CodeBERTa-small, query + schema** (trained on a laptop CPU) | **87.4** | **87.6** |

* **Repair:** 86.3% of erroneous test queries get a verified fix, and 63.4% are restored exactly to the original.
  Syntax and unknown-table errors are 93–96% exact. Mean repair time is 33 ms.
* **Analyzer:** 96.5% of the 8,034 human-written Spider queries pass; the rest are genuine issues.
  The access-policy check is 100% correct on 400 query/policy pairs.
* **NL→SQL** (150 Spider-dev questions, same questions for both generators):

  | Generator | Valid SQL: raw → verified + repaired | Correct result: raw → final |
  |---|---|---|
  | T5-small (text-to-SQL) | 34.7% → 66.7% | 16.0% → 22.0% |
  | **Qwen2.5-Coder-0.5B-Instruct** (default) | **54.0% → 88.0%** | **40.0% → 54.7%** |

* The classifier's weakest class is `UNKNOWN_COLUMN` (F1 71%). A larger encoder can be trained on a free GPU
  with [`notebooks/train_codebert_gpu.ipynb`](notebooks/train_codebert_gpu.ipynb).

A 5-minute demo script with likely reviewer questions is in [`docs/DEMO.md`](docs/DEMO.md).

## How it works

```
                 ┌───────────────────────────────┐
 query ─────────►│ Analyzer (deterministic)      │── issues, verified class ──┐
 schema ────────►│  1. SQLite compiles the query │                            │
 access policy ─►│     against an empty DB with  │                            ▼
                 │     the schema (EXPLAIN only) │                   ┌────────────────┐
                 │  2. AST rules (sqlglot):      │                   │ Diagnosis      │── API / UI / CLI
                 │     GROUP BY, NULL, joins,    │                   │ service (fuse) │
                 │     types, aliases, policy    │                   └────────────────┘
                 └───────────────────────────────┘                            ▲
 query + schema ─► Transformer classifier (CodeBERTa / CodeBERT) ─ probabilities, attributions
 erroneous query ─► Repair engine: candidate fixes per issue → re-analyze → keep smallest verified fix → repeat
 question ───────► code LLM (Qwen2.5-Coder-0.5B) → candidate → verify → [more candidates] → repair
```

* **Analyzer** (`analysis/`): the query is compiled (never executed) by SQLite against an in-memory database
  built from the schema, which yields precise grammar, name-resolution and several semantic errors. Rules on the
  sqlglot AST add what SQLite tolerates but standard SQL rejects (`= NULL`, non-grouped columns, missing join
  conditions, type mismatches, duplicate aliases, self-comparisons) and the access-policy check. Without a
  schema it still checks grammar and schema-independent semantics.
* **Classifier** (`models/classifier.py`): a code transformer fine-tuned on `query </s></s> schema` pairs to
  predict the seven learnable classes. It provides calibrated probabilities and integrated-gradients
  explanations. The analyzer's verdict wins whenever it finds a problem; the model is decisive only when no
  schema is available, and flags anything it disagrees with.
* **Repair engine** (`repair/`): for the primary issue it proposes candidates — edit-distance keyword
  correction, fuzzy and foreign-key-aware table/column matching, alias qualification, FK-inferred join
  conditions, AST rewrites (`IS NULL`, `HAVING`, `GROUP BY`, scalar subqueries, casts) and a bounded
  single-edit search — re-analyzes every candidate and keeps the smallest verified fix, iterating for
  multi-error queries. It never reports success for a query that does not pass the analyzer.
* **Dataset** (`data_pipeline/`): errors are injected into Spider gold queries with 25+ span-level mutation
  operators; every sample is kept only if the analyzer independently confirms its label. Surface features
  (keyword case, spacing, literals, alias names) are randomised for all classes. Train/validation/test use
  disjoint databases (test = Spider-dev databases), see [`data/processed/dataset_report.md`](data/processed/dataset_report.md).

## Quick start

Run the demo (about 5 minutes, no training needed):

```bash
git clone https://github.com/thilaganiniyavan/SQLDiagnose.git && cd SQLDiagnose
make setup        # Python virtual environment + dependencies, and builds the web app (needs Node.js 20+)
make model        # downloads the fine-tuned classifier (310 MB) from the GitHub release
make api          # web app at http://localhost:8000, REST API under /api/v1, API docs at /docs
```

The NL→SQL generator (Qwen2.5-Coder-0.5B, ~1 GB) downloads automatically on the first *Question → SQL*
request. To run queries on the example databases' real data, download Spider once with `make data`.
`make help` lists all tasks; each one is a plain command you can also run directly.

Reproduce the research results:

```bash
make data         # downloads Spider and rebuilds the dataset (identical to data/processed)
make train        # CodeBERTa-small, 3 epochs (several hours on CPU; GPU: notebooks/train_codebert_gpu.ipynb)
make finetune     # 2 further epochs from the best checkpoint (how the released model was produced)
make evaluate     # -> reports/evaluation_report.md, reports/results.json, reports/figures/
make test
```

`python -m training.train --resume` continues an interrupted run.

Without a trained checkpoint the API and UI still work with the deterministic analyzer and repair engine;
`GET /api/v1/health` reports `model_loaded: false`.

> If your virtual environment was moved, the `pip`/`uvicorn` launchers may point to the old path.
> `python -m <tool>` always works.

### Web app

A React single-page app (`frontend/`) served by the API from the same origin:

| Page | What it does |
|---|---|
| **Diagnose & repair** | SQL editor with schema-aware autocompletion (`Ctrl/⌘+Enter` to run), one example per error class, verdict + every issue, verified fix with a word diff and *Use this query*, read-only **run on real data**, classifier probabilities and token attributions, shareable links (`/?q=…&db=…&run=1`) |
| **Question → SQL** | asks the code LLM in a background job with live progress (queue, model loading, generation), shows the verified SQL, every candidate with its verdict, and the answer from the database |
| **Batch check** | paste queries (per line or `;`-separated) or drop a CSV; class breakdown, filters, search, expandable rows with fixes, CSV/JSON export |
| **Schemas** | import from CREATE TABLE (7 dialects), a SQLite file (optionally kept so queries can be run), a live PostgreSQL/MySQL database or JSON; rename, export, delete; browse the 160 example databases |
| **History** | every diagnosis, question and batch, searchable and filterable; reopen any result |
| **Research results** | the evaluation (`reports/results.json`) as charts or tables, plus the report figures |
| **Service status** | loaded models, data, counters since start, the error taxonomy |

The selected database and its **access policy** (lock icons next to tables and columns) apply to every page.
History and saved schemas are kept per browser in a SQLite workspace on the server (`data/workspace/`); the
browser sends an anonymous id (`X-Client-Id`), there are no accounts.

Development with hot reload: `make api` in one terminal and `make dev` in another (http://localhost:5173,
proxied to the API). `make lint`, `make test` (pytest + Vitest) and `make e2e` (Playwright, real browser against
the real API) check it; see [`frontend/README.md`](frontend/README.md).

### Command line

```bash
python cli.py diagnose "SELECT nme FROM singer" --db concert_singer
python cli.py repair   "SELEC name, count(*) FORM singr WHERE age > 'thirty'" --db concert_singer
#  VERIFIED FIX
#    SELECT name, COUNT(*) FROM singer WHERE age > 30 GROUP BY name
python cli.py nl2sql   "How many singers are from France?" --db concert_singer
python cli.py diagnose "SELECT * FROM staff" --ddl schema.sql --dialect postgres --restrict staff
python cli.py dbs      # bundled example schemas (the 160 Spider databases)
```

### REST API (`/api/v1`)

| Method | Path | Purpose |
|---|---|---|
| POST | `/diagnose` | classify one query (`explain: true` adds token attributions) |
| POST | `/repair` | diagnosis + verified repair |
| POST | `/batch` | many queries against one schema, optional repair |
| POST | `/upload` | CSV with a `query` column (optional `db_id` column) |
| POST | `/analyze` | diagnosis (+ attributions) and verified repair in one call; recorded in the history |
| POST | `/nl2sql` | question → verified SQL (candidates, repair, diagnosis), synchronous |
| POST/GET/DELETE | `/nl2sql/jobs`, `/nl2sql/jobs/{id}` | the same as a background job: submit, poll progress, cancel while queued |
| POST | `/execute` | run a read-only SELECT on an example database's data or an uploaded SQLite file (row and time limits) |
| GET | `/databases` | example databases with size and whether their data is installed |
| GET/POST/PATCH/DELETE | `/workspace/schemas[/{id}]`, `/workspace/schemas/sqlite` | saved schemas (any request can use one with `schema_id`) |
| GET/DELETE | `/workspace/history[/{id}]` | run history (`kind`, `search`, `limit`, `offset`) |
| GET | `/results`, `/results/figures/{name}` | evaluation results and figures |
| GET | `/schemas`, `/schemas/{db_id}` | bundled example schemas |
| POST | `/schemas/parse-ddl`, `/schemas/parse-sqlite`, `/schemas/parse-live` | import a schema |
| GET | `/health`, `/labels`, `/metrics` | service status, taxonomy, counters |

Every query endpoint takes the schema inline (`database_schema`), as a saved workspace schema (`schema_id`) or by
name (`db_id`), plus an optional
`access_policy` (`{"restricted_tables": [...], "restricted_columns": ["table.col"]}`):

```bash
curl -s localhost:8000/api/v1/repair -H 'content-type: application/json' \
  -d '{"query": "SELECT name FROM singr", "db_id": "concert_singer"}'
```

Schema format: `{"table": {"columns": {"col": "TYPE"}, "primary_keys": [...], "foreign_keys": [{"column": .., "target_table": .., "target_column": ..}]}}`.

### Docker

```bash
docker compose -f deployment/docker-compose.yml up --build     # web app + API on http://localhost:8000
```

The image builds the web app in a Node stage and serves it from the API. The workspace (history, saved schemas,
uploaded databases) and the generator download live in named volumes; the example databases' data is mounted
read-only from `data/raw` when present.

### Deployment notes

* Run one worker process (`uvicorn … --workers 1`): NL→SQL jobs and the models live in the process. Put a
  reverse proxy (TLS, request size limit, rate limiting) in front when exposing it.
* There is no authentication. `X-Client-Id` only separates browsers' workspaces; anyone who can reach the server
  can use it. Set `SQLDIAGNOSE_LIVE_SCHEMA=false` on shared deployments (live introspection connects to any host
  the user names; the compose file does this).
* Query execution is read-only by construction: the database is opened in read-only mode, an SQLite authorizer
  allows only reads, and a progress handler stops queries after `execution.timeout_s` (5 s); at most
  `execution.max_rows` rows are returned.
* Configuration: `configs/api_config.yaml`, overridable with the `SQLDIAGNOSE_*` environment variables listed at
  its top.

## Project layout

```
analysis/          schema model + deterministic analyzer
data_pipeline/     Spider loader, mutation operators, dataset builder, schema parsers
models/            domain (labels, entities, interfaces), transformer classifier, NL2SQL generators
repair/            verified repair engine
services/          use cases: diagnosis (analyzer + model + repair), NL2SQL, schema registry,
                   workspace store, read-only query execution, background jobs
training/          fine-tuning script (CPU/GPU, resumable)
evaluation/        metrics, baselines, explainability, full evaluation → reports/
deployment/        FastAPI app (REST API + serves the web app), Dockerfile, compose file
frontend/          React + TypeScript web app (Vite, Tailwind CSS, CodeMirror), unit and end-to-end tests
notebooks/         GPU training notebook (Colab/Kaggle)
configs/           training / API / UI configuration
data/processed/    generated dataset (jsonl/csv), schemas.json, dataset report
docs/design/       original research and design documents
tests/             pytest suite (python -m pytest)
```

## Testing

```bash
python -m pytest            # analyzer, repair, mutations, dataset integrity, schema parsing, services, API
make test-web               # web app unit tests (Vitest + Testing Library)
make e2e                    # web app end to end in Chromium against the running API (Playwright)
```

## Limitations

* Errors in the dataset are injected synthetically; natural errors (e.g. from text-to-SQL models) are evaluated
  separately in the report.
* Labels come from the analyzer, so the classifier learns to approximate it; the analyzer itself is audited
  against human-written Spider queries.
* Checks follow SQLite semantics plus portable (PostgreSQL/MySQL-strict) rules; engine-specific behaviour can differ.
* `DATATYPE_MISMATCH` repairs are only proposed when the intended value is recoverable (`'5'`, `'thirty'`, casts).
