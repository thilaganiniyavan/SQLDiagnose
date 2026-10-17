# routes.py
# Clean Architecture: Frameworks & Drivers
# REST endpoints. All CPU-bound handlers are sync functions, which FastAPI runs in a thread pool.

import csv
import io
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse

from analysis.schema import DatabaseSchema
from data_pipeline import schema_parser
from models.domain.labels import CLASS_DESCRIPTIONS, CLASS_NAMES
from services.executor import ExecutionError, execute_readonly
from services.jobs import QueueFull
from .schemas import (AccessPolicy, AnalyzeRequest, BatchRequest, DiagnoseRequest, DiagnosisResponse, ExecuteRequest,
                      HealthResponse, MetricsResponse, NL2SQLRequest, ParseDDLRequest, ParseLiveRequest,
                      RepairRequest, RepairResponse, SavedSchemaCreate, SavedSchemaUpdate, SchemaContext)

router = APIRouter()

SQLITE_MAGIC = b"SQLite format 3\x00"
_CLIENT_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
MAX_SCHEMA_TABLES = 2000


def _state(request: Request):
    return request.app.state.ctx


def _client(request: Request) -> Optional[str]:
    """Browser workspace id (X-Client-Id). Requests without one are not recorded in a history."""
    cid = request.headers.get("x-client-id")
    if cid is None:
        return None
    if not _CLIENT_ID.match(cid):
        raise HTTPException(400, "Invalid X-Client-Id header (8-64 letters, digits, '-' or '_').")
    return cid


def _workspace(request: Request):
    ws = _state(request).workspace
    if ws is None:
        raise HTTPException(503, "The workspace store is disabled (api.workspace_dir).")
    return ws


def _owner(request: Request) -> str:
    return _client(request) or "default"


def _saved_schema(request: Request, schema_id: str) -> Dict[str, Any]:
    saved = _workspace(request).get_schema(_owner(request), schema_id)
    if saved is None:
        raise HTTPException(404, f"Unknown saved schema '{schema_id}'.")
    return saved


def _schema(request: Request, body: SchemaContext) -> Optional[DatabaseSchema]:
    policy = body.access_policy.model_dump() if body.access_policy else None
    inline = body.database_schema
    if not inline and body.schema_id:
        saved = _saved_schema(request, body.schema_id)
        inline, policy = saved["database_schema"], policy or saved["access_policy"]
    try:
        return _state(request).registry.resolve(inline, body.db_id, policy)
    except KeyError:
        raise HTTPException(404, f"Unknown example database '{body.db_id}'. See GET /api/v1/schemas.")
    except (TypeError, ValueError, AttributeError) as e:
        raise HTTPException(422, f"Invalid database_schema: {e}")


def _context(body: SchemaContext) -> Dict[str, Any]:
    """What a history entry needs to re-run a request with the same schema."""
    ctx: Dict[str, Any] = {}
    if body.database_schema:
        ctx["database_schema"] = body.database_schema
    elif body.schema_id:
        ctx["schema_id"] = body.schema_id
    elif body.db_id:
        ctx["db_id"] = body.db_id
    if body.access_policy and (body.access_policy.restricted_tables or body.access_policy.restricted_columns):
        ctx["access_policy"] = body.access_policy.model_dump()
    return ctx


def _record(request: Request, kind: str, title: str, context: Dict[str, Any], error_class: Optional[str],
            summary: Dict[str, Any], result: Any) -> Optional[str]:
    ctx, cid = _state(request), _client(request)
    if cid is None or ctx.workspace is None:
        return None
    return ctx.workspace.add_history(cid, kind, title, context, error_class, summary, result)


def _validate_schema_dict(schema: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(schema, dict) or not schema:
        raise HTTPException(422, "The schema must be a non-empty object of tables.")
    if len(schema) > MAX_SCHEMA_TABLES:
        raise HTTPException(413, f"At most {MAX_SCHEMA_TABLES} tables per schema.")
    try:
        normalized = DatabaseSchema.from_dict(schema, "check").to_dict()
    except (TypeError, ValueError, AttributeError, KeyError) as e:
        raise HTTPException(422, f"Invalid database_schema: {e}")
    empty = [t for t, info in normalized.items() if not info["columns"]]
    if empty:
        raise HTTPException(422, f"Invalid database_schema: table '{empty[0]}' has no columns.")
    return normalized


def _diagnosis_response(diag, latency_ms: float, explanation=None) -> DiagnosisResponse:
    d = diag.to_dict()
    return DiagnosisResponse(description=CLASS_DESCRIPTIONS[d["error_class"]], explanation=explanation,
                             latency_ms=round(latency_ms, 2), **d)


# ---------------------------------------------------------------------- meta
@router.get("/health", response_model=HealthResponse)
def health(request: Request):
    ctx = _state(request)
    return HealthResponse(status="ok", version=ctx.version, model_loaded=ctx.diagnosis.model_loaded,
                          model=ctx.model_info, generator_loaded=ctx.generator_ready,
                          generator=ctx.generator_name, generator_error=ctx.generator_error,
                          example_databases=len(ctx.registry.names()),
                          executable_databases=len(ctx.executable_db_ids()),
                          live_schema_enabled=ctx.enable_live_schema,
                          results_available=bool(ctx.reports_dir and (ctx.reports_dir / "results.json").is_file()),
                          workspace_enabled=ctx.workspace is not None)


@router.get("/labels")
def labels() -> List[Dict[str, Any]]:
    return [{"id": i, "name": n, "description": CLASS_DESCRIPTIONS[n]} for i, n in enumerate(CLASS_NAMES)]


@router.get("/metrics", response_model=MetricsResponse)
def metrics(request: Request):
    return _state(request).metrics.snapshot()


# ---------------------------------------------------------------------- schemas
@router.get("/schemas")
def list_schemas(request: Request) -> List[str]:
    return _state(request).registry.names()


@router.get("/databases")
def list_databases(request: Request) -> List[Dict[str, Any]]:
    """Example databases with their size and whether queries can be run against real data."""
    ctx = _state(request)
    executable = set(ctx.executable_db_ids())
    out = []
    for name in ctx.registry.names():
        raw = ctx.registry.raw(name) or {}
        out.append({"db_id": name, "tables": len(raw),
                    "columns": sum(len(t.get("columns", {})) for t in raw.values()),
                    "executable": name in executable})
    return out


@router.get("/schemas/{db_id}")
def get_schema(request: Request, db_id: str) -> Dict[str, Any]:
    ctx = _state(request)
    reg = ctx.registry
    schema = reg.get(db_id)
    if schema is None:
        raise HTTPException(404, f"Unknown example database '{db_id}'.")
    return {"db_id": db_id, "database_schema": reg.raw(db_id), "ddl": schema.to_ddl(),
            "executable": ctx.example_db_path(db_id) is not None}


@router.post("/schemas/parse-ddl")
def parse_ddl(body: ParseDDLRequest) -> Dict[str, Any]:
    try:
        return {"database_schema": schema_parser.parse_ddl(body.ddl, body.dialect)}
    except Exception as e:
        raise HTTPException(422, f"Could not parse DDL: {e}")


def _read_sqlite(data: bytes, limit_mb: int) -> Dict[str, Any]:
    if len(data) > limit_mb * 1024 * 1024:
        raise HTTPException(413, f"SQLite file larger than {limit_mb} MB.")
    if not data.startswith(SQLITE_MAGIC):
        raise HTTPException(422, "Not a SQLite database file.")
    try:
        schema = schema_parser.parse_sqlite_bytes(data)
    except Exception as e:
        raise HTTPException(422, f"Could not read SQLite file: {e}")
    if not schema:
        raise HTTPException(422, "The SQLite file contains no tables.")
    return schema


@router.post("/schemas/parse-sqlite")
async def parse_sqlite(file: UploadFile = File(...)) -> Dict[str, Any]:
    return {"database_schema": _read_sqlite(await file.read(), 200)}


@router.post("/schemas/parse-live")
def parse_live(request: Request, body: ParseLiveRequest) -> Dict[str, Any]:
    if not _state(request).enable_live_schema:
        raise HTTPException(403, "Live database introspection is disabled (api.enable_live_schema_parsing).")
    try:
        if body.engine == "postgresql":
            schema = schema_parser.parse_postgresql(body.connection.get("dsn", ""))
        else:
            schema = schema_parser.parse_mysql(body.connection)
    except RuntimeError as e:
        raise HTTPException(501, str(e))
    except Exception as e:
        raise HTTPException(502, f"Could not read the database schema: {e}")
    return {"database_schema": schema}


# ---------------------------------------------------------------------- diagnosis & repair
@router.post("/diagnose", response_model=DiagnosisResponse)
@router.post("/predict", response_model=DiagnosisResponse, include_in_schema=False)
def diagnose(request: Request, body: DiagnoseRequest):
    ctx = _state(request)
    schema = _schema(request, body)
    t = time.perf_counter()
    diag = ctx.diagnosis.diagnose(body.query, schema, use_model=body.use_model)
    latency = (time.perf_counter() - t) * 1000
    explanation = None
    if body.explain:
        if not ctx.diagnosis.model_loaded:
            explanation = {"error": "No classifier checkpoint is loaded, so token attributions are unavailable."}
        else:
            explanation = ctx.diagnosis.explain(body.query, schema, body.explain_method)
    ctx.metrics.record_diagnosis(diag.error_class, latency)
    ctx.metrics.count("diagnose")
    return _diagnosis_response(diag, latency, explanation)


@router.post("/analyze")
def analyze(request: Request, body: AnalyzeRequest) -> Dict[str, Any]:
    """Diagnosis (optionally with token attributions) plus a verified repair when the query is wrong."""
    ctx = _state(request)
    schema = _schema(request, body)
    t = time.perf_counter()
    diag = ctx.diagnosis.diagnose(body.query, schema)
    diag_ms = (time.perf_counter() - t) * 1000
    explanation = None
    if body.explain:
        if not ctx.diagnosis.model_loaded:
            explanation = {"error": "No classifier checkpoint is loaded, so token attributions are unavailable."}
        else:
            explanation = ctx.diagnosis.explain(body.query, schema, body.explain_method)
    result = None
    if body.repair and diag.is_error:
        result = ctx.diagnosis.repair(body.query, schema)
        ctx.metrics.record_repair(result.success)
    latency = (time.perf_counter() - t) * 1000
    ctx.metrics.record_diagnosis(diag.error_class, diag_ms)
    ctx.metrics.count("analyze")
    response = {"diagnosis": _diagnosis_response(diag, diag_ms, explanation).model_dump(),
                "repair": result.to_dict() if result else None, "latency_ms": round(latency, 2)}
    summary = {"is_error": diag.is_error, "confidence": diag.confidence,
               "repaired_query": result.repaired_query if result and result.success else None,
               "repair_success": result.success if result else None}
    response["history_id"] = _record(request, "analyze", body.query, _context(body), diag.error_class,
                                     summary, response)
    return response


@router.post("/repair", response_model=RepairResponse)
def repair(request: Request, body: RepairRequest):
    ctx = _state(request)
    schema = _schema(request, body)
    t = time.perf_counter()
    diag = ctx.diagnosis.diagnose(body.query, schema)
    result = ctx.diagnosis.repair(body.query, schema)
    latency = (time.perf_counter() - t) * 1000
    ctx.metrics.record_diagnosis(diag.error_class, latency)
    if diag.is_error:
        ctx.metrics.record_repair(result.success)
    ctx.metrics.count("repair")
    return RepairResponse(diagnosis=_diagnosis_response(diag, latency), repair=result.to_dict(),
                          latency_ms=round(latency, 2))


def _batch(ctx, queries: List[str], schemas: List[Optional[DatabaseSchema]], do_repair: bool) -> List[Dict]:
    if len(queries) > ctx.max_batch:
        raise HTTPException(413, f"At most {ctx.max_batch} queries per batch.")
    t = time.perf_counter()
    diags = ctx.diagnosis.diagnose_batch(queries, schemas)
    per_query = (time.perf_counter() - t) * 1000 / max(1, len(queries))
    out = []
    for q, s, d in zip(queries, schemas, diags):
        ctx.metrics.record_diagnosis(d.error_class, per_query)
        row = {"query": q, "is_error": d.is_error, "error_class": d.error_class, "confidence": d.confidence,
               "decided_by": d.decided_by,
               "issues": [i.message for i in d.analysis.issues] if d.analysis else [],
               "model_prediction": d.model.error_class if d.model else None}
        if do_repair and d.is_error:
            r = ctx.diagnosis.repair(q, s)
            ctx.metrics.record_repair(r.success)
            row.update(repaired_query=r.repaired_query if r.success else None, repair_success=r.success,
                       repair_explanation=r.explanation)
        out.append(row)
    return out


def _record_batch(request: Request, title: str, context: Dict[str, Any], rows: List[Dict]):
    errors = sum(r["is_error"] for r in rows)
    summary = {"total": len(rows), "errors": errors,
               "repaired": sum(bool(r.get("repair_success")) for r in rows)}
    _record(request, "batch", title, context, None, summary, rows)


@router.post("/batch")
def batch(request: Request, body: BatchRequest) -> List[Dict]:
    ctx = _state(request)
    schema = _schema(request, body)
    ctx.metrics.count("batch")
    rows = _batch(ctx, body.queries, [schema] * len(body.queries), body.repair)
    _record_batch(request, f"{len(rows)} pasted queries", _context(body), rows)
    return rows


@router.post("/upload")
async def upload(request: Request, file: UploadFile = File(...), repair: bool = True,
                 db_id: Optional[str] = None, schema_id: Optional[str] = None,
                 access_policy: Optional[str] = Form(None, description="JSON access policy applied to every row")) -> List[Dict]:
    """CSV with a `query` column and optionally a `db_id` column (per-row example database).
    Rows without a db_id use the `db_id` or saved `schema_id` query parameter."""
    ctx = _state(request)
    policy = None
    if access_policy:
        try:
            policy = AccessPolicy.model_validate_json(access_policy).model_dump()
        except ValueError as e:
            raise HTTPException(422, f"Invalid access_policy: {e}")
    raw = await file.read()
    try:
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    except UnicodeDecodeError:
        raise HTTPException(422, "The CSV file must be UTF-8 encoded.")
    if not rows or "query" not in rows[0]:
        raise HTTPException(422, "The CSV needs a header row with a 'query' column.")
    default_schema = (_schema(request, SchemaContext(schema_id=schema_id, access_policy=policy))
                      if schema_id and not db_id else None)
    queries, schemas = [], []
    for r in rows:
        rid = (r.get("db_id") or db_id or "").strip()
        schema = ctx.registry.get(rid) if rid else default_schema
        if rid and schema is None:
            raise HTTPException(404, f"Unknown example database '{rid}' in CSV.")
        if rid and policy:
            schema = schema.with_policy(policy)
        queries.append(r["query"] or "")
        schemas.append(schema)
    ctx.metrics.count("upload")
    out = _batch(ctx, queries, schemas, repair)
    context = {"db_id": db_id} if db_id else ({"schema_id": schema_id} if schema_id else {})
    _record_batch(request, f"{file.filename or 'upload.csv'} ({len(out)} queries)", context, out)
    return out


# ---------------------------------------------------------------------- NL2SQL
@router.post("/nl2sql")
@router.post("/generate_sql", include_in_schema=False)
def nl2sql(request: Request, body: NL2SQLRequest) -> Dict[str, Any]:
    ctx = _state(request)
    schema = _schema(request, body)
    if schema is None or not schema.tables:
        raise HTTPException(422, "NL2SQL needs a schema (database_schema or db_id).")
    service = ctx.nl2sql()
    if service is None:
        raise HTTPException(503, f"The SQL generator could not be loaded: {ctx.generator_error}")
    t = time.perf_counter()
    result = service.run(body.question, schema, body.num_candidates)
    result["latency_ms"] = round((time.perf_counter() - t) * 1000, 1)
    ctx.metrics.count("nl2sql")
    return result


# ---------------------------------------------------------------------- NL2SQL jobs (asynchronous)
def _nl2sql_job(request: Request, body: NL2SQLRequest, schema: DatabaseSchema, client: Optional[str]):
    ctx = _state(request)
    context = _context(body)

    def work(job):
        if not ctx.generator_ready:
            job.phase = "loading_model"
        service = ctx.nl2sql()
        if service is None:
            raise RuntimeError(f"The SQL generator could not be loaded: {ctx.generator_error}")
        job.phase = "generating"
        t = time.perf_counter()
        result = service.run(body.question, schema, body.num_candidates)
        result["latency_ms"] = round((time.perf_counter() - t) * 1000, 1)
        ctx.metrics.count("nl2sql")
        if client and ctx.workspace is not None:
            result["history_id"] = ctx.workspace.add_history(
                client, "nl2sql", body.question, context,
                (result.get("diagnosis") or {}).get("error_class"),
                {"status": result["status"], "sql": result["sql"]}, result)
        return result

    return work


@router.post("/nl2sql/jobs", status_code=202)
def submit_nl2sql(request: Request, body: NL2SQLRequest) -> Dict[str, Any]:
    """Queues a question; poll GET /nl2sql/jobs/{id}. Generation takes tens of seconds on a CPU."""
    ctx = _state(request)
    schema = _schema(request, body)
    if schema is None or not schema.tables:
        raise HTTPException(422, "NL2SQL needs a schema (database_schema, schema_id or db_id).")
    if not ctx.generator_name:
        raise HTTPException(503, "No SQL generator is configured (api.generator).")
    if ctx.generator_error:
        ctx.retry_generator()
    client = _client(request)
    try:
        job = ctx.jobs.submit("nl2sql", _nl2sql_job(request, body, schema, client), owner=client or "default",
                              question=body.question)
    except QueueFull as e:
        raise HTTPException(429, str(e))
    return ctx.jobs.describe(job)


def _job(request: Request, job_id: str):
    job = _state(request).jobs.get(job_id)
    if job is None or job.owner != (_client(request) or "default"):
        raise HTTPException(404, "Unknown or expired job.")
    return job


@router.get("/nl2sql/jobs/{job_id}")
def get_nl2sql_job(request: Request, job_id: str) -> Dict[str, Any]:
    return _state(request).jobs.describe(_job(request, job_id))


@router.delete("/nl2sql/jobs/{job_id}")
def cancel_nl2sql_job(request: Request, job_id: str) -> Dict[str, Any]:
    ctx = _state(request)
    job = _job(request, job_id)
    if not ctx.jobs.cancel(job.id):
        raise HTTPException(409, "Only queued jobs can be cancelled; this one has already started.")
    return ctx.jobs.describe(job)


# ---------------------------------------------------------------------- execution
@router.post("/execute")
def execute(request: Request, body: ExecuteRequest) -> Dict[str, Any]:
    """Runs a read-only query against a real database: a downloaded example database (db_id) or an
    uploaded SQLite file kept with a saved schema (schema_id)."""
    ctx = _state(request)
    if body.schema_id:
        _saved_schema(request, body.schema_id)
        path = _workspace(request).database_path(_owner(request), body.schema_id)
        if path is None:
            raise HTTPException(409, "This saved schema has no database file; import it from a SQLite file to run queries.")
    elif body.db_id:
        if ctx.registry.raw(body.db_id) is None:
            raise HTTPException(404, f"Unknown example database '{body.db_id}'.")
        path = ctx.example_db_path(body.db_id)
        if path is None:
            raise HTTPException(409, "The data for this example database has not been downloaded (run `make data`).")
    else:
        raise HTTPException(422, "Give a db_id or a schema_id to run the query against.")
    try:
        result = execute_readonly(path, body.query, min(body.max_rows, ctx.exec_max_rows), ctx.exec_timeout_s)
    except ExecutionError as e:
        raise HTTPException(422, str(e))
    ctx.metrics.count("execute")
    return result


# ---------------------------------------------------------------------- workspace: saved schemas
@router.get("/workspace/schemas")
def list_saved_schemas(request: Request) -> List[Dict[str, Any]]:
    return _workspace(request).list_schemas(_owner(request))


@router.post("/workspace/schemas", status_code=201)
def create_saved_schema(request: Request, body: SavedSchemaCreate) -> Dict[str, Any]:
    schema = _validate_schema_dict(body.database_schema)
    policy = body.access_policy.model_dump() if body.access_policy else None
    return _workspace(request).create_schema(_owner(request), body.name.strip(), body.source, schema, policy)


@router.post("/workspace/schemas/sqlite", status_code=201)
async def create_saved_schema_from_sqlite(request: Request, file: UploadFile = File(...),
                                          name: Optional[str] = Form(None),
                                          keep_database: bool = Form(True)) -> Dict[str, Any]:
    """Imports a SQLite file. With keep_database the file is stored so queries can be run against it."""
    ctx = _state(request)
    ws = _workspace(request)
    data = await file.read()
    schema = _read_sqlite(data, ctx.max_upload_mb)
    label = (name or Path(file.filename or "database.sqlite").stem or "database").strip()[:120]
    return ws.create_schema(_owner(request), label, "sqlite", schema, None, data if keep_database else None)


@router.get("/workspace/schemas/{schema_id}")
def get_saved_schema(request: Request, schema_id: str) -> Dict[str, Any]:
    saved = _saved_schema(request, schema_id)
    saved["ddl"] = DatabaseSchema.from_dict(saved["database_schema"], saved["name"]).to_ddl()
    return saved


@router.patch("/workspace/schemas/{schema_id}")
def update_saved_schema(request: Request, schema_id: str, body: SavedSchemaUpdate) -> Dict[str, Any]:
    schema = _validate_schema_dict(body.database_schema) if body.database_schema is not None else None
    policy = body.access_policy.model_dump() if body.access_policy else None
    saved = _workspace(request).update_schema(_owner(request), schema_id, body.name.strip() if body.name else None,
                                              schema, policy, body.clear_access_policy)
    if saved is None:
        raise HTTPException(404, f"Unknown saved schema '{schema_id}'.")
    return saved


@router.delete("/workspace/schemas/{schema_id}", status_code=204)
def delete_saved_schema(request: Request, schema_id: str):
    if not _workspace(request).delete_schema(_owner(request), schema_id):
        raise HTTPException(404, f"Unknown saved schema '{schema_id}'.")
    return Response(status_code=204)


# ---------------------------------------------------------------------- workspace: history
@router.get("/workspace/history")
def list_history(request: Request, kind: Optional[str] = Query(None, pattern="^(analyze|nl2sql|batch)$"),
                 search: Optional[str] = Query(None, max_length=200), limit: int = Query(50, ge=1, le=200),
                 offset: int = Query(0, ge=0)) -> Dict[str, Any]:
    return _workspace(request).list_history(_owner(request), kind, search, limit, offset)


@router.get("/workspace/history/{history_id}")
def get_history(request: Request, history_id: str) -> Dict[str, Any]:
    item = _workspace(request).get_history(_owner(request), history_id)
    if item is None:
        raise HTTPException(404, "Unknown history entry.")
    return item


@router.delete("/workspace/history/{history_id}", status_code=204)
def delete_history(request: Request, history_id: str):
    if not _workspace(request).delete_history(_owner(request), history_id):
        raise HTTPException(404, "Unknown history entry.")
    return Response(status_code=204)


@router.delete("/workspace/history")
def clear_history(request: Request) -> Dict[str, int]:
    return {"deleted": _workspace(request).clear_history(_owner(request))}


# ---------------------------------------------------------------------- research results
@router.get("/results")
def results(request: Request) -> Dict[str, Any]:
    """The evaluation results (reports/results.json) plus the list of available figures."""
    reports = _state(request).reports_dir
    path = reports / "results.json" if reports else None
    if path is None or not path.is_file():
        raise HTTPException(404, "No evaluation results; run `make evaluate`.")
    data = json.loads(path.read_text())
    figures = reports / "figures"
    data["figures"] = sorted(p.name for p in figures.glob("*.png")) if figures.is_dir() else []
    return data


@router.get("/results/figures/{name}")
def result_figure(request: Request, name: str):
    reports = _state(request).reports_dir
    figures = reports / "figures" if reports else None
    if figures is None or not figures.is_dir() or name not in {p.name for p in figures.glob("*.png")}:
        raise HTTPException(404, "Unknown figure.")
    return FileResponse(figures / name, media_type="image/png", headers={"Cache-Control": "public, max-age=3600"})
