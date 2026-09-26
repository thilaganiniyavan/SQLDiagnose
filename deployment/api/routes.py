# routes.py
# Clean Architecture: Frameworks & Drivers
# REST endpoints. All CPU-bound handlers are sync functions, which FastAPI runs in a thread pool.

import csv
import io
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from analysis.schema import DatabaseSchema
from data_pipeline import schema_parser
from models.domain.labels import CLASS_DESCRIPTIONS, CLASS_NAMES
from .schemas import (BatchRequest, DiagnoseRequest, DiagnosisResponse, HealthResponse, MetricsResponse,
                      NL2SQLRequest, ParseDDLRequest, ParseLiveRequest, RepairRequest, RepairResponse,
                      SchemaContext)

router = APIRouter()


def _state(request: Request):
    return request.app.state.ctx


def _schema(request: Request, body: SchemaContext) -> Optional[DatabaseSchema]:
    policy = body.access_policy.model_dump() if body.access_policy else None
    try:
        return _state(request).registry.resolve(body.database_schema, body.db_id, policy)
    except KeyError:
        raise HTTPException(404, f"Unknown example database '{body.db_id}'. See GET /api/v1/schemas.")
    except (TypeError, ValueError, AttributeError) as e:
        raise HTTPException(422, f"Invalid database_schema: {e}")


def _diagnosis_response(diag, latency_ms: float, explanation=None) -> DiagnosisResponse:
    d = diag.to_dict()
    return DiagnosisResponse(description=CLASS_DESCRIPTIONS[d["error_class"]], explanation=explanation,
                             latency_ms=round(latency_ms, 2), **d)


# ---------------------------------------------------------------------- meta
@router.get("/health", response_model=HealthResponse)
def health(request: Request):
    ctx = _state(request)
    return HealthResponse(status="ok", version=ctx.version, model_loaded=ctx.diagnosis.model_loaded,
                          model=ctx.model_info, generator_loaded=ctx.generator is not None,
                          generator=ctx.generator_name, example_databases=len(ctx.registry.names()))


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


@router.get("/schemas/{db_id}")
def get_schema(request: Request, db_id: str) -> Dict[str, Any]:
    reg = _state(request).registry
    schema = reg.get(db_id)
    if schema is None:
        raise HTTPException(404, f"Unknown example database '{db_id}'.")
    return {"db_id": db_id, "database_schema": reg.raw(db_id), "ddl": schema.to_ddl()}


@router.post("/schemas/parse-ddl")
def parse_ddl(body: ParseDDLRequest) -> Dict[str, Any]:
    try:
        return {"database_schema": schema_parser.parse_ddl(body.ddl, body.dialect)}
    except Exception as e:
        raise HTTPException(422, f"Could not parse DDL: {e}")


@router.post("/schemas/parse-sqlite")
async def parse_sqlite(file: UploadFile = File(...)) -> Dict[str, Any]:
    data = await file.read()
    if len(data) > 200 * 1024 * 1024:
        raise HTTPException(413, "SQLite file larger than 200 MB.")
    if not data.startswith(b"SQLite format 3\x00"):
        raise HTTPException(422, "Not a SQLite database file.")
    try:
        return {"database_schema": schema_parser.parse_sqlite_bytes(data)}
    except Exception as e:
        raise HTTPException(422, f"Could not read SQLite file: {e}")


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


@router.post("/batch")
def batch(request: Request, body: BatchRequest) -> List[Dict]:
    ctx = _state(request)
    schema = _schema(request, body)
    ctx.metrics.count("batch")
    return _batch(ctx, body.queries, [schema] * len(body.queries), body.repair)


@router.post("/upload")
async def upload(request: Request, file: UploadFile = File(...), repair: bool = True,
                 db_id: Optional[str] = None) -> List[Dict]:
    """CSV with a `query` column and optionally a `db_id` column (per-row example database)."""
    ctx = _state(request)
    raw = await file.read()
    try:
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    except UnicodeDecodeError:
        raise HTTPException(422, "The CSV file must be UTF-8 encoded.")
    if not rows or "query" not in rows[0]:
        raise HTTPException(422, "The CSV needs a header row with a 'query' column.")
    queries, schemas = [], []
    for r in rows:
        rid = (r.get("db_id") or db_id or "").strip()
        schema = ctx.registry.get(rid) if rid else None
        if rid and schema is None:
            raise HTTPException(404, f"Unknown example database '{rid}' in CSV.")
        queries.append(r["query"] or "")
        schemas.append(schema)
    ctx.metrics.count("upload")
    return _batch(ctx, queries, schemas, repair)


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
