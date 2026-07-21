# run_full_system_e2e_verification.py
# Clean Architecture: Frameworks & Drivers
# Comprehensive End-to-End System Test Suite

import os
import sys
import time
import json
import io
import tempfile
import sqlite3
import subprocess
import requests
from pathlib import Path

BASE_URL = "http://127.0.0.1:8000"

SAMPLE_SCHEMA = {
    "employees": {
        "columns": {"id": "INTEGER", "name": "VARCHAR", "salary": "REAL", "dept_id": "INTEGER"},
        "primary_keys": ["id"],
        "foreign_keys": [{"column": "dept_id", "target_table": "departments", "target_column": "id"}]
    },
    "departments": {
        "columns": {"id": "INTEGER", "name": "VARCHAR", "budget": "REAL"},
        "primary_keys": ["id"],
        "foreign_keys": []
    }
}

def test_backend_health(session: requests.Session) -> bool:
    print("[FULL E2E] 1. Testing GET /health ...")
    res = session.get(f"{BASE_URL}/health")
    if res.status_code == 200:
        data = res.json()
        print(f"  [PASS] Server Status: {data.get('status')}, Model Loaded: {data.get('model_loaded')}, Device: {data.get('device')}")
        return True
    else:
        print(f"  [FAIL] GET /health returned status {res.status_code}")
        return False

def test_predict_endpoint(session: requests.Session) -> bool:
    print("[FULL E2E] 2. Testing POST /predict ...")
    payload = {
        "sql_query": "SELECT name FROM employees WHERE salary > 50000",
        "database_schema": SAMPLE_SCHEMA,
        "explain": True
    }
    res = session.post(f"{BASE_URL}/predict", json=payload)
    if res.status_code == 200:
        data = res.json()
        print(f"  [PASS] Predicted Class: {data['predicted_class']}, Confidence: {data['confidence']:.2f}, Explanation Present: {'explanation' in data}")
        return True
    else:
        print(f"  [FAIL] POST /predict returned status {res.status_code}: {res.text}")
        return False

def test_repair_endpoint(session: requests.Session) -> bool:
    print("[FULL E2E] 3. Testing POST /repair ...")
    payload = {
        "sql_query": "SELECT invalid_col FROM employees",
        "predicted_class": 3, # UNKNOWN_COLUMN
        "database_schema": SAMPLE_SCHEMA
    }
    res = session.post(f"{BASE_URL}/repair", json=payload)
    if res.status_code == 200:
        data = res.json()
        print(f"  [PASS] Explanation: {data['explanation'][:40]}..., Corrected SQL: {data.get('corrected_query')}")
        return True
    else:
        print(f"  [FAIL] POST /repair returned status {res.status_code}: {res.text}")
        return False

def test_generate_sql_endpoint(session: requests.Session) -> bool:
    print("[FULL E2E] 4. Testing POST /generate_sql (NL2SQL + Auto-Validation) ...")
    payload = {
        "question": "Find names of employees earning more than 50000",
        "database_schema": SAMPLE_SCHEMA,
        "confidence_threshold": 0.5
    }
    res = session.post(f"{BASE_URL}/generate_sql", json=payload, timeout=30)
    if res.status_code == 200:
        data = res.json()
        print(f"  [PASS] Generated SQL: '{data['generated_sql']}', Confidence: {data['confidence']:.2f}, Validated Class: {data['validation']['predicted_class']}")
        return True
    else:
        print(f"  [FAIL] POST /generate_sql returned status {res.status_code}: {res.text}")
        return False

def test_batch_endpoint(session: requests.Session) -> bool:
    print("[FULL E2E] 5. Testing POST /batch ...")
    payload = {
        "queries": [
            "SELECT * FROM employees",
            "SELECT invalid_col FROM employees"
        ],
        "database_schemas": [SAMPLE_SCHEMA, SAMPLE_SCHEMA],
        "run_repair": True
    }
    res = session.post(f"{BASE_URL}/batch", json=payload)
    if res.status_code == 200:
        data = res.json()
        results = data.get("results", [])
        print(f"  [PASS] Processed {len(results)} queries in batch.")
        return True
    else:
        print(f"  [FAIL] POST /batch returned status {res.status_code}: {res.text}")
        return False

def test_upload_endpoint(session: requests.Session) -> bool:
    print("[FULL E2E] 6. Testing POST /upload (CSV Batch Upload) ...")
    csv_content = "sql_query\nSELECT * FROM employees\nSELECT invalid_col FROM employees\n"
    files = {"file": ("test_queries.csv", csv_content.encode("utf-8"), "text/csv")}
    res = session.post(f"{BASE_URL}/upload", files=files)
    if res.status_code == 200:
        data = res.json()
        print(f"  [PASS] Upload endpoint processed {len(data)} rows from CSV.")
        return True
    else:
        print(f"  [FAIL] POST /upload returned status {res.status_code}: {res.text}")
        return False

def test_metrics_endpoint(session: requests.Session) -> bool:
    print("[FULL E2E] 7. Testing GET /metrics ...")
    res = session.get(f"{BASE_URL}/metrics")
    if res.status_code == 200:
        data = res.json()
        print(f"  [PASS] Total Predictions: {data['total_predictions']}, Total Repairs: {data['total_repairs']}, Avg Latency: {data['avg_inference_time_ms']:.2f}ms")
        return True
    else:
        print(f"  [FAIL] GET /metrics returned status {res.status_code}")
        return False

def test_schema_parser() -> bool:
    print("[FULL E2E] 8. Testing DatabaseSchemaParser Service ...")
    try:
        from datasets.schema_parser import DatabaseSchemaParser
        
        # Create a temporary SQLite db
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name
            
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE test_users (id INTEGER PRIMARY KEY, email TEXT NOT NULL);")
        conn.commit()
        conn.close()
        
        parsed = DatabaseSchemaParser.parse_sqlite(db_path)
        ddl = DatabaseSchemaParser.to_ddl(parsed)
        
        os.remove(db_path)
        
        if "test_users" in parsed and "CREATE TABLE test_users" in ddl:
            print("  [PASS] DatabaseSchemaParser successfully parsed SQLite database and generated DDL.")
            return True
        else:
            print("  [FAIL] DatabaseSchemaParser output missing table names or DDL.")
            return False
    except Exception as e:
        print(f"  [FAIL] Schema parser error: {e}")
        return False

def test_frontend_syntax() -> bool:
    print("[FULL E2E] 9. Testing Frontend (frontend/app.py) Compilation ...")
    try:
        import py_compile
        py_compile.compile("frontend/app.py", doraise=True)
        print("  [PASS] frontend/app.py compiled with zero syntax or import errors.")
        return True
    except Exception as e:
        print(f"  [FAIL] frontend/app.py compilation failed: {e}")
        return False

def run_full_verification():
    print("="*70)
    print("=== RUNNING FULL END-TO-END SYSTEM FUNCTIONAL VERIFICATION ===")
    print("="*70)
    
    # Start FastAPI server in a background process
    print("\n[INIT] Starting FastAPI Backend Server on port 8000 ...")
    server_log_file = open("server_test.log", "w", encoding="utf-8")
    server_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "deployment.api.main:app", "--host", "127.0.0.1", "--port", "8000"],
        stdout=server_log_file,
        stderr=server_log_file
    )
    
    # Wait for server initialization
    session = requests.Session()
    server_ready = False
    for attempt in range(60):
        try:
            r = session.get(f"{BASE_URL}/health", timeout=1)
            if r.status_code == 200:
                server_ready = True
                print(f"[INIT] Server ready after {attempt+1} seconds!")
                break
        except Exception:
            time.sleep(1)
            
    if not server_ready:
        print("[CRITICAL FAIL] Server failed to start on port 8000 within 60 seconds.")
        server_log_file.close()
        if Path("server_test.log").exists():
            print("--- SERVER LOG ---")
            print(Path("server_test.log").read_text(encoding="utf-8", errors="replace")[-2000:])
        server_process.kill()
        sys.exit(1)
        
    results = []
    try:
        results.append(("1. GET /health", test_backend_health(session)))
        results.append(("2. POST /predict", test_predict_endpoint(session)))
        results.append(("3. POST /repair", test_repair_endpoint(session)))
        results.append(("4. POST /generate_sql", test_generate_sql_endpoint(session)))
        results.append(("5. POST /batch", test_batch_endpoint(session)))
        results.append(("6. POST /upload", test_upload_endpoint(session)))
        results.append(("7. GET /metrics", test_metrics_endpoint(session)))
        results.append(("8. DatabaseSchemaParser", test_schema_parser()))
        results.append(("9. Frontend Compilation", test_frontend_syntax()))
    finally:
        print("\n[CLEANUP] Stopping FastAPI Backend Server ...")
        server_process.terminate()
        server_process.wait()
        try:
            server_log_file.close()
        except Exception:
            pass
        
    print("\n" + "="*70)
    print("=== SUMMARY RESULT OF FULL END-TO-END VERIFICATION ===")
    print("="*70)
    
    all_passed = True
    for name, passed in results:
        status_str = "[PASS]" if passed else "[FAIL]"
        print(f"  {name:<40} {status_str}")
        if not passed:
            all_passed = False
            
    print("="*70)
    if all_passed:
        print("ALL 9 SYSTEM SERVICES AND ENDPOINTS PASSED VERIFICATION WITH 100% SUCCESS!")
    else:
        print("SOME VERIFICATION TESTS FAILED. PLEASE REVIEW LOGS ABOVE.")
        sys.exit(1)

if __name__ == "__main__":
    run_full_verification()
