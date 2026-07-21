# routes.py
# Clean Architecture: Frameworks & Drivers
# Endpoint definitions routing request inputs to models & repair use cases.

import time
import csv
import io
import torch
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from .schemas import (
    SQLClassificationRequest,
    SQLClassificationResponse,
    ClassProbability,
    SQLRepairRequest,
    SQLRepairResponse,
    BatchRequest,
    BatchResponse,
    HealthResponse,
    MetricsResponse,
    SQLGenerationRequest,
    SQLGenerationResponse
)

router = APIRouter()

CLASS_NAMES = [
    "CORRECT",
    "SYNTAX_ERROR",
    "UNKNOWN_TABLE",
    "UNKNOWN_COLUMN",
    "DATATYPE_MISMATCH",
    "DUPLICATE_ALIAS",
    "PERMISSION_DENIED",
    "SEMANTIC_ERROR"
]

@router.post("/predict", response_model=SQLClassificationResponse, summary="Classify SQL Query Error Status")
async def predict_query(request: Request, body: SQLClassificationRequest):
    """
    Evaluates a SQL query and returns predicted error classes, probability metrics, and optional XAI explanations.
    """
    classifier = request.app.state.classifier
    tokenizer = request.app.state.tokenizer
    
    if not classifier or not tokenizer:
        raise HTTPException(status_code=503, detail="Model weights are not loaded.")
        
    start_time = time.time()
    
    # 1. Tokenize query
    inputs = tokenizer(body.sql_query, return_tensors="pt")
    device = next(classifier.model.parameters()).device
    tokenized_inputs = {k: v.to(device) if isinstance(v, torch.Tensor) else v for k, v in inputs.items()}
    
    # 2. Forward pass for prediction probabilities
    try:
        probs = classifier.predict(tokenized_inputs)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Inference execution failed: {str(e)}")
        
    pred_idx = int(torch.argmax(torch.tensor(probs)).item())
    confidence = probs[pred_idx]
    is_error = (pred_idx != 0)
    
    # 3. Generate XAI explanation if requested
    explanation_data = None
    if body.explain:
        try:
            explanation_data = classifier.predict_with_explanation(
                query=body.sql_query,
                tokenizer=tokenizer,
                save_dir=None # Return data only, do not write files
            )
            # Remove redundant prediction fields from explainer payload
            if "probabilities" in explanation_data:
                del explanation_data["probabilities"]
            if "predicted_class" in explanation_data:
                del explanation_data["predicted_class"]
        except Exception as e:
            # Fallback warning but do not crash response
            explanation_data = {"error": f"Failed to compute attributions: {str(e)}"}
            
    latency_ms = (time.time() - start_time) * 1000.0
    
    # 4. Compile probabilities breakdown list
    probs_list = [
        ClassProbability(class_name=CLASS_NAMES[i], probability=float(probs[i]))
        for i in range(len(CLASS_NAMES))
    ]
    
    # Update global metrics
    request.app.state.total_predictions += 1
    request.app.state.total_inference_time_ms += latency_ms
    request.app.state.error_class_counts[CLASS_NAMES[pred_idx]] += 1
    
    return SQLClassificationResponse(
        is_error=is_error,
        predicted_class=CLASS_NAMES[pred_idx],
        confidence=confidence,
        probabilities=probs_list,
        explanation=explanation_data,
        inference_time_ms=latency_ms
    )

@router.post("/repair", response_model=SQLRepairResponse, summary="Repair SQL Query Errors")
async def repair_query(request: Request, body: SQLRepairRequest):
    """
    Applies rule-based or fuzzy schema matching repairs to resolve classified error categories.
    """
    repair_engine = request.app.state.repair_engine
    classifier = request.app.state.classifier
    tokenizer = request.app.state.tokenizer
    
    if not repair_engine:
        raise HTTPException(status_code=503, detail="Repair engine is not initialized.")
        
    # 1. Resolve error class index
    pred_idx = body.predicted_class
    confidence = 1.0
    
    if pred_idx is None:
        # Run classification internally
        if not classifier or not tokenizer:
            raise HTTPException(status_code=500, detail="Cannot run classification to determine error class: model not loaded.")
        inputs = tokenizer(body.sql_query, return_tensors="pt")
        device = next(classifier.model.parameters()).device
        tokenized_inputs = {k: v.to(device) if isinstance(v, torch.Tensor) else v for k, v in inputs.items()}
        probs = classifier.predict(tokenized_inputs)
        pred_idx = int(torch.argmax(torch.tensor(probs)).item())
        confidence = probs[pred_idx]
        
    # 2. Run Repair Engine
    try:
        repair_result = repair_engine.repair(
            query=body.sql_query,
            predicted_class=pred_idx,
            confidence=confidence,
            schema=body.database_schema
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Repair execution failed: {str(e)}")
        
    # Update global metrics
    request.app.state.total_repairs += 1
    
    return SQLRepairResponse(
        explanation=repair_result["explanation"],
        suggested_correction=repair_result["suggested_correction"],
        corrected_query=repair_result["corrected_query"],
        confidence_score=repair_result["confidence_score"]
    )

@router.post("/batch", response_model=BatchResponse, summary="Batch Classify and Repair SQL Queries")
async def batch_process(request: Request, body: BatchRequest):
    """
    Handles sequential batch classification and optional auto-repairs for arrays of SQL statements.
    """
    results = []
    schemas = body.database_schemas or [None] * len(body.queries)
    
    if len(schemas) < len(body.queries):
        # Pad schema list
        schemas.extend([None] * (len(body.queries) - len(schemas)))
        
    for i, q in enumerate(body.queries):
        schema = schemas[i]
        
        # Classification sub-routine
        # Perform predict
        pred_res = await predict_query(
            request, 
            SQLClassificationRequest(sql_query=q, database_schema=schema, explain=False)
        )
        
        result_payload = {
            "query": q,
            "classification": pred_res.dict()
        }
        
        if body.run_repair:
            # Map name to index
            pred_class_str = pred_res.predicted_class
            pred_idx = CLASS_NAMES.index(pred_class_str)
            
            repair_res = await repair_query(
                request,
                SQLRepairRequest(sql_query=q, predicted_class=pred_idx, database_schema=schema)
            )
            result_payload["repair"] = repair_res.dict()
            
        results.append(result_payload)
        
    return BatchResponse(results=results)

@router.post("/upload", response_model=List[Dict[str, Any]], summary="Batch Process SQL Queries from Uploaded CSV File")
async def upload_csv_file(request: Request, file: UploadFile = File(...)):
    """
    Accepts an uploaded CSV file containing SQL queries under a 'sql_query' column,
    runs batch prediction & repair, and returns the compiled JSON records list.
    """
    contents = await file.read()
    decoded = contents.decode("utf-8")
    
    # Read CSV file
    csv_file = io.StringIO(decoded)
    reader = csv.DictReader(csv_file)
    
    queries = []
    schemas = []
    
    for row in reader:
        q = row.get("sql_query") or row.get("query")
        if q:
            queries.append(q)
            # Check for optional schema catalog definition in columns
            s_str = row.get("database_schema") or row.get("schema")
            schema_dict = None
            if s_str:
                try:
                    schema_dict = json.loads(s_str)
                except Exception:
                    pass
            schemas.append(schema_dict)
            
    if not queries:
        raise HTTPException(status_code=400, detail="Uploaded CSV contains no valid 'sql_query' or 'query' columns.")
        
    # Execute batch request logic
    batch_body = BatchRequest(queries=queries, database_schemas=schemas, run_repair=True)
    batch_res = await batch_process(request, batch_body)
    return batch_res.results

@router.get("/health", response_model=HealthResponse, summary="API Health Check")
async def health_check(request: Request):
    """
    Performs container status and ML weight validation.
    """
    classifier = request.app.state.classifier
    device = next(classifier.model.parameters()).device.type if classifier else "unknown"
    return HealthResponse(
        status="healthy",
        model_loaded=(classifier is not None),
        device=device
    )

@router.get("/metrics", response_model=MetricsResponse, summary="Retrieve API Operational Metrics")
async def get_metrics(request: Request):
    """
    Retrieves operational telemetry logs and error class counts.
    """
    total_preds = request.app.state.total_predictions
    avg_inference = 0.0
    if total_preds > 0:
        avg_inference = request.app.state.total_inference_time_ms / total_preds
        
    return MetricsResponse(
        total_predictions=total_preds,
        total_repairs=request.app.state.total_repairs,
        error_class_counts=request.app.state.error_class_counts,
        avg_inference_time_ms=avg_inference
    )

@router.post("/generate_sql", response_model=SQLGenerationResponse, summary="Translate Natural Language to SQL and Validate")
async def generate_sql_endpoint(request: Request, body: SQLGenerationRequest):
    """
    Generates SQL from a natural language question and validates it using the classifier.
    If classification predicts an error, it passes the query to the repair engine.
    """
    generator_service = getattr(request.app.state, "generator_service", None)
    if not generator_service:
        try:
            from models.generator import SQLGeneratorService
            generator_service = SQLGeneratorService()
            request.app.state.generator_service = generator_service
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"SQL Generator service initialization error: {str(e)}")
            
    classifier = getattr(request.app.state, "classifier", None)
    tokenizer = getattr(request.app.state, "tokenizer", None)
    repair_engine = getattr(request.app.state, "repair_engine", None)
        
    # 1. Run local Text-to-SQL generation
    try:
        gen_result = generator_service.generate_sql(
            question=body.question,
            schema=body.database_schema,
            confidence_threshold=body.confidence_threshold or 0.5
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SQL Generation failed: {str(e)}")
        
    generated_sql = gen_result["generated_sql"]
    confidence = gen_result["confidence"]
    alternatives = gen_result["alternatives"]
    warning = gen_result["warning"]
    inference_time_ms = gen_result["inference_time_ms"]
    
    # 2. Run generated query through the validation sequence
    if not classifier or not tokenizer:
         raise HTTPException(status_code=500, detail="Classifier or tokenizer is not loaded.")
         
    inputs = tokenizer(generated_sql, return_tensors="pt")
    device = next(classifier.model.parameters()).device
    tokenized_inputs = {k: v.to(device) if isinstance(v, torch.Tensor) else v for k, v in inputs.items()}
    
    try:
        probs = classifier.predict(tokenized_inputs)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Validation inference failed: {str(e)}")
        
    pred_idx = int(torch.argmax(torch.tensor(probs)).item())
    pred_class_str = CLASS_NAMES[pred_idx]
    is_error = (pred_idx != 0)
    
    probs_list = [
        ClassProbability(class_name=CLASS_NAMES[idx], probability=float(probs[idx]))
        for idx in range(len(CLASS_NAMES))
    ]
    
    validation_payload = {
        "is_error": is_error,
        "predicted_class": pred_class_str,
        "confidence": float(probs[pred_idx]),
        "probabilities": [p.dict() for p in probs_list]
    }
    
    # 3. If there is an error, invoke the repair engine
    repaired_sql = None
    explanation_data = None
    
    if is_error and repair_engine:
        try:
            repair_result = repair_engine.repair(
                query=generated_sql,
                predicted_class=pred_idx,
                confidence=float(probs[pred_idx]),
                schema=body.database_schema
            )
            repaired_sql = repair_result["corrected_query"]
            explanation_data = {
                "explanation": repair_result["explanation"],
                "suggested_correction": repair_result["suggested_correction"]
            }
        except Exception as e:
            explanation_data = {"error": f"Repair execution failed: {str(e)}"}
            
    # Update global metrics for predictions
    request.app.state.total_predictions += 1
    request.app.state.error_class_counts[pred_class_str] += 1
    
    return SQLGenerationResponse(
        generated_sql=generated_sql,
        confidence=confidence,
        validation=validation_payload,
        repaired_sql=repaired_sql,
        explanation=explanation_data,
        inference_time_ms=inference_time_ms,
        warning=warning,
        alternatives=alternatives
    )

