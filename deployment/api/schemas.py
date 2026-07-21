# schemas.py
# Clean Architecture: Interface Adapters
# Pydantic schemas validating external HTTP inputs and outputs.

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

class SQLClassificationRequest(BaseModel):
    sql_query: str = Field(..., description="The raw SQL query string to evaluate.")
    database_schema: Optional[Dict[str, Any]] = Field(None, description="Optional active database schema for semantic analysis.")
    explain: Optional[bool] = Field(False, description="Whether to include token importance and attention weights.")

class ClassProbability(BaseModel):
    class_name: str = Field(..., description="Name of the error or status category.")
    probability: float = Field(..., description="Model confidence probability (0.0 to 1.0).")

class SQLClassificationResponse(BaseModel):
    is_error: bool = Field(..., description="Flag indicating if the SQL contains an error.")
    predicted_class: str = Field(..., description="The predicted error class or CORRECT.")
    confidence: float = Field(..., description="Softmax confidence probability for the predicted class.")
    probabilities: List[ClassProbability] = Field(..., description="Confidence scores for all supported classes.")
    explanation: Optional[Dict[str, Any]] = Field(None, description="Explainable AI attribution scores and attention matrices if requested.")
    inference_time_ms: float = Field(..., description="Latency of the classification pass in milliseconds.")

class SQLRepairRequest(BaseModel):
    sql_query: str = Field(..., description="The raw SQL query string to repair.")
    predicted_class: Optional[int] = Field(None, description="Optional pre-classified error index (0-7). If not provided, the classifier will be executed first.")
    database_schema: Optional[Dict[str, Any]] = Field(None, description="Active database schema catalog for auto-correction.")

class SQLRepairResponse(BaseModel):
    explanation: str = Field(..., description="Explanation of the error category.")
    suggested_correction: str = Field(..., description="Recommended fix action description.")
    corrected_query: Optional[str] = Field(None, description="The auto-corrected SQL query if a fix was feasible.")
    confidence_score: float = Field(..., description="Confidence associated with the classification/repair action.")

class BatchRequest(BaseModel):
    queries: List[str] = Field(..., description="List of SQL query strings to batch process.")
    database_schemas: Optional[List[Optional[Dict[str, Any]]]] = Field(None, description="Optional parallel list of database schemas.")
    run_repair: Optional[bool] = Field(False, description="Whether to also run the auto-repair engine for each query.")

class BatchResponse(BaseModel):
    results: List[Dict[str, Any]] = Field(..., description="List of prediction (and optional repair) results matching input queries.")

class HealthResponse(BaseModel):
    status: str = Field("healthy", description="API health status.")
    model_loaded: bool = Field(..., description="Flag indicating if transformer weights are successfully loaded in memory.")
    device: str = Field(..., description="Execution hardware target (e.g. cpu, cuda).")

class MetricsResponse(BaseModel):
    total_predictions: int = Field(..., description="Cumulative number of single query classifications processed.")
    total_repairs: int = Field(..., description="Cumulative number of query auto-repairs executed.")
    error_class_counts: Dict[str, int] = Field(..., description="Breakdown of predictions across categories.")
    avg_inference_time_ms: float = Field(..., description="Average classification inference latency in milliseconds.")

class SQLGenerationRequest(BaseModel):
    question: str = Field(..., description="The natural language question to translate to SQL.")
    database_schema: Dict[str, Any] = Field(..., description="The active database schema catalog.")
    confidence_threshold: Optional[float] = Field(0.5, description="Threshold below which warning and alternatives are generated.")

class SQLGenerationResponse(BaseModel):
    generated_sql: str = Field(..., description="The generated SQL query.")
    confidence: float = Field(..., description="The confidence score of the generation (0.0 to 1.0).")
    validation: Dict[str, Any] = Field(..., description="Validation metadata from the classifier (is_error, predicted_class, etc.).")
    repaired_sql: Optional[str] = Field(None, description="The auto-corrected SQL query if errors were detected and repaired.")
    explanation: Optional[Dict[str, Any]] = Field(None, description="Attributions and repair explanations.")
    inference_time_ms: float = Field(..., description="Generation inference latency in milliseconds.")
    warning: Optional[str] = Field(None, description="Warning if confidence is below threshold.")
    alternatives: Optional[List[str]] = Field(None, description="Top alternative SQL candidates if confidence is low.")

