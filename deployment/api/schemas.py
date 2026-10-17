# schemas.py
# Clean Architecture: Frameworks & Drivers
# Request/response models of the REST API.

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

MAX_QUERY_CHARS = 20_000


class AccessPolicy(BaseModel):
    restricted_tables: List[str] = Field(default_factory=list)
    restricted_columns: List[str] = Field(default_factory=list, description='"table.column" entries')


class SchemaContext(BaseModel):
    """An inline schema, a saved workspace schema or a bundled example database (in that order of precedence)."""
    database_schema: Optional[Dict[str, Any]] = Field(
        None, description='{"table": {"columns": {"col": "TYPE"}, "primary_keys": [...], "foreign_keys": [...]}}')
    db_id: Optional[str] = Field(None, description="Name of a bundled example database (see GET /schemas)")
    schema_id: Optional[str] = Field(None, max_length=64, description="Id of a saved workspace schema")
    access_policy: Optional[AccessPolicy] = None


class DiagnoseRequest(SchemaContext):
    query: str = Field(..., min_length=1, max_length=MAX_QUERY_CHARS)
    explain: bool = Field(False, description="Include token attributions from the model")
    explain_method: Literal["gxi", "ig"] = "gxi"
    use_model: bool = True


class RepairRequest(SchemaContext):
    query: str = Field(..., min_length=1, max_length=MAX_QUERY_CHARS)


class AnalyzeRequest(SchemaContext):
    """Diagnosis and, when the query is wrong, a verified repair in one call."""
    query: str = Field(..., min_length=1, max_length=MAX_QUERY_CHARS)
    explain: bool = False
    explain_method: Literal["gxi", "ig"] = "gxi"
    repair: bool = True


class ExecuteRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=MAX_QUERY_CHARS)
    db_id: Optional[str] = None
    schema_id: Optional[str] = Field(None, max_length=64)
    max_rows: int = Field(200, ge=1, le=1000)


class BatchRequest(SchemaContext):
    queries: List[str] = Field(..., min_length=1)
    repair: bool = False


class NL2SQLRequest(SchemaContext):
    question: str = Field(..., min_length=3, max_length=2_000)
    num_candidates: int = Field(3, ge=1, le=5)


class SavedSchemaCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    source: Literal["json", "ddl", "sqlite", "live", "example"] = "json"
    database_schema: Dict[str, Any]
    access_policy: Optional[AccessPolicy] = None


class SavedSchemaUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    database_schema: Optional[Dict[str, Any]] = None
    access_policy: Optional[AccessPolicy] = None
    clear_access_policy: bool = False


class ParseDDLRequest(BaseModel):
    ddl: str = Field(..., min_length=10, max_length=200_000)
    dialect: Literal["sqlite", "postgres", "mysql", "tsql", "oracle", "snowflake", "bigquery"] = "sqlite"


class ParseLiveRequest(BaseModel):
    engine: Literal["postgresql", "mysql"]
    connection: Dict[str, Any] = Field(
        ..., description='postgresql: {"dsn": "dbname=... user=..."}; mysql: {"host":..,"user":..,"password":..,"database":..}')


class DiagnosisResponse(BaseModel):
    query: str
    is_error: bool
    error_class: str
    description: str
    confidence: float
    decided_by: str
    analysis: Optional[Dict[str, Any]] = None
    model: Optional[Dict[str, Any]] = None
    notes: List[str] = Field(default_factory=list)
    explanation: Optional[Dict[str, Any]] = None
    latency_ms: float


class RepairResponse(BaseModel):
    diagnosis: DiagnosisResponse
    repair: Dict[str, Any]
    latency_ms: float


class HealthResponse(BaseModel):
    status: str
    version: str
    model_loaded: bool
    model: Optional[Dict[str, Any]] = None
    generator_loaded: bool
    generator: Optional[str] = None
    generator_error: Optional[str] = None
    example_databases: int
    executable_databases: int = 0
    live_schema_enabled: bool = False
    results_available: bool = False
    workspace_enabled: bool = False


class MetricsResponse(BaseModel):
    uptime_s: float
    requests: Dict[str, int]
    diagnoses: int
    repairs: int
    repairs_successful: int
    mean_diagnosis_latency_ms: float
    class_counts: Dict[str, int]
