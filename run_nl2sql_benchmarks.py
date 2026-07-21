# run_nl2sql_benchmarks.py
# Clean Architecture: Frameworks & Drivers
# Text-to-SQL Benchmarking & Performance Profiling Suite

import os
import sys
import time
import json
import sqlite3
import torch
import psutil
from typing import Dict, Any, List
from models.generator import SQLGeneratorService
from datasets.schema_parser import DatabaseSchemaParser

# Test Cases covering Selection, Filtering, Aggregation, GROUP BY, HAVING, ORDER BY, JOIN, and Nested queries
NL2SQL_TEST_CASES = [
    {
        "category": "Selection",
        "question": "List all department names",
        "ref_sql": "SELECT name FROM departments;",
        "eval_sql": "SELECT name FROM departments"
    },
    {
        "category": "Filtering",
        "question": "Find names of employees earning more than 50000",
        "ref_sql": "SELECT name FROM employees WHERE salary > 50000;",
        "eval_sql": "SELECT name FROM employees WHERE salary > 50000"
    },
    {
        "category": "Aggregation",
        "question": "Get the maximum budget across all departments",
        "ref_sql": "SELECT MAX(budget) FROM departments;",
        "eval_sql": "SELECT MAX(budget) FROM departments"
    },
    {
        "category": "GROUP BY",
        "question": "Show department IDs and total salary for each department",
        "ref_sql": "SELECT dept_id, SUM(salary) FROM employees GROUP BY dept_id;",
        "eval_sql": "SELECT dept_id, SUM(salary) FROM employees GROUP BY dept_id"
    },
    {
        "category": "HAVING",
        "question": "Show department IDs where average salary is greater than 60000",
        "ref_sql": "SELECT dept_id FROM employees GROUP BY dept_id HAVING AVG(salary) > 60000;",
        "eval_sql": "SELECT dept_id FROM employees GROUP BY dept_id HAVING AVG(salary) > 60000"
    },
    {
        "category": "ORDER BY",
        "question": "List employee names ordered by salary descending",
        "ref_sql": "SELECT name FROM employees ORDER BY salary DESC;",
        "eval_sql": "SELECT name FROM employees ORDER BY salary DESC"
    },
    {
        "category": "JOIN",
        "question": "List employee name and their department name",
        "ref_sql": "SELECT employees.name, departments.name FROM employees JOIN departments ON employees.dept_id = departments.id;",
        "eval_sql": "SELECT employees.name, departments.name FROM employees JOIN departments ON employees.dept_id = departments.id"
    },
    {
        "category": "Nested Query",
        "question": "List employee names earning more than the average salary",
        "ref_sql": "SELECT name FROM employees WHERE salary > (SELECT AVG(salary) FROM employees);",
        "eval_sql": "SELECT name FROM employees WHERE salary > (SELECT AVG(salary) FROM employees)"
    }
]

SCHEMA = {
    "employees": {
        "columns": {"id": "INTEGER", "name": "TEXT", "salary": "REAL", "dept_id": "INTEGER"},
        "primary_keys": ["id"],
        "foreign_keys": [{"column": "dept_id", "target_table": "departments", "target_column": "id"}]
    },
    "departments": {
        "columns": {"id": "INTEGER", "name": "TEXT", "budget": "REAL"},
        "primary_keys": ["id"],
        "foreign_keys": []
    }
}

def setup_in_memory_db() -> sqlite3.Connection:
    """
    Creates an in-memory SQLite database populated with mock data matching the test schema.
    """
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    
    # Create tables
    cursor.execute("""
    CREATE TABLE departments (
        id INTEGER PRIMARY KEY,
        name TEXT,
        budget REAL
    );
    """)
    cursor.execute("""
    CREATE TABLE employees (
        id INTEGER PRIMARY KEY,
        name TEXT,
        salary REAL,
        dept_id INTEGER,
        FOREIGN KEY (dept_id) REFERENCES departments(id)
    );
    """)
    
    # Insert mock data
    cursor.executemany("INSERT INTO departments VALUES (?, ?, ?);", [
        (1, "Engineering", 150000.0),
        (2, "Sales", 80000.0),
        (3, "HR", 50000.0)
    ])
    cursor.executemany("INSERT INTO employees VALUES (?, ?, ?, ?);", [
        (101, "Alice", 75000.0, 1),
        (102, "Bob", 62000.0, 1),
        (103, "Charlie", 45000.0, 2),
        (104, "David", 35000.0, 3),
        (105, "Eve", 90000.0, 1)
    ])
    conn.commit()
    return conn

def normalize_sql(sql: str) -> str:
    """
    Performs basic SQL normalization (lowercasing, whitespace compression, semicolon stripping).
    """
    sql = sql.lower().strip()
    if sql.endswith(";"):
        sql = sql[:-1]
    return " ".join(sql.split())

def execute_query(conn: sqlite3.Connection, query: str) -> List[Any]:
    """
    Executes a query and returns the results. Normalizes syntax for execution comparison.
    """
    cursor = conn.cursor()
    try:
        # SQLite queries require semicolons or not, handles gracefully
        cursor.execute(query)
        return cursor.fetchall()
    except Exception as e:
        return [f"Execution Error: {str(e)}"]

def run_benchmarks():
    print("=== STARTING NL2SQL BENCHMARKING AND PERFORMANCE PROFILING ===")
    
    # Measure memory usage before model loading
    process = psutil.Process(os.getpid())
    mem_before = process.memory_info().rss / (1024 * 1024) # in MB
    cuda_mem_before = torch.cuda.memory_allocated() / (1024 * 1024) if torch.cuda.is_available() else 0
    
    # 1. Initialize Generator Service
    start_load = time.time()
    generator = SQLGeneratorService()
    load_time = (time.time() - start_load) * 1000.0
    
    # Measure memory usage after model loading
    mem_after = process.memory_info().rss / (1024 * 1024) # in MB
    cuda_mem_after = torch.cuda.memory_allocated() / (1024 * 1024) if torch.cuda.is_available() else 0
    
    mem_delta = mem_after - mem_before
    cuda_mem_delta = cuda_mem_after - cuda_mem_before
    
    print(f"[METRIC] Model Load Time: {load_time:.2f} ms")
    print(f"[METRIC] Host Memory Delta: {mem_delta:.2f} MB")
    if torch.cuda.is_available():
        print(f"[METRIC] CUDA VRAM Delta: {cuda_mem_delta:.2f} MB")
        
    # 2. Setup mock database
    db_conn = setup_in_memory_db()
    
    # 3. Evaluate test cases
    results = []
    exact_matches = 0
    exec_matches = 0
    latencies = []
    
    for case in NL2SQL_TEST_CASES:
        category = case["category"]
        question = case["question"]
        ref_sql = case["ref_sql"]
        
        print(f"\n[EVAL] Category: {category} | Question: '{question}'")
        
        # Run generation
        gen_res = generator.generate_sql(question, SCHEMA)
        generated_sql = gen_res["generated_sql"]
        confidence = gen_res["confidence"]
        latency = gen_res["inference_time_ms"]
        latencies.append(latency)
        
        print(f"  Generated: '{generated_sql}'")
        print(f"  Confidence: {confidence:.2f} | Latency: {latency:.2f} ms")
        
        # Normalize for EM
        norm_ref = normalize_sql(ref_sql)
        norm_gen = normalize_sql(generated_sql)
        is_em = (norm_ref == norm_gen)
        if is_em:
            exact_matches += 1
            
        # Execute for EX
        ref_results = execute_query(db_conn, ref_sql)
        gen_results = execute_query(db_conn, generated_sql)
        
        # Sort results to avoid order discrepancies unless ORDER BY is specified
        if "ORDER BY" not in ref_sql.upper():
            try:
                ref_results = sorted(ref_results, key=lambda x: str(x))
                gen_results = sorted(gen_results, key=lambda x: str(x))
            except Exception:
                pass
                
        is_ex = (ref_results == gen_results)
        if is_ex:
            exec_matches += 1
            
        print(f"  Exact Match: {is_em} | Execution Accuracy: {is_ex}")
        
        results.append({
            "category": category,
            "question": question,
            "reference_sql": ref_sql,
            "generated_sql": generated_sql,
            "confidence": confidence,
            "latency_ms": latency,
            "exact_match": is_em,
            "execution_accuracy": is_ex
        })
        
    db_conn.close()
    
    # 4. Compile statistics
    total_cases = len(NL2SQL_TEST_CASES)
    em_rate = (exact_matches / total_cases) * 100
    ex_rate = (exec_matches / total_cases) * 100
    avg_latency = sum(latencies) / total_cases
    
    print("\n" + "="*50)
    print("=== BENCHMARK SUMMARY ===")
    print(f"Total Test Cases: {total_cases}")
    print(f"Exact Match Rate: {em_rate:.2f}% ({exact_matches}/{total_cases})")
    print(f"Execution Accuracy: {ex_rate:.2f}% ({exec_matches}/{total_cases})")
    print(f"Average Generation Latency: {avg_latency:.2f} ms")
    print("="*50)
    
    # Save results to file
    benchmark_summary = {
        "metrics": {
            "total_cases": total_cases,
            "exact_match_rate": em_rate,
            "execution_accuracy": ex_rate,
            "average_latency_ms": avg_latency,
            "model_load_time_ms": load_time,
            "host_memory_delta_mb": mem_delta,
            "cuda_vram_delta_mb": cuda_mem_delta
        },
        "runs": results
    }
    
    reports_dir = os.path.join(os.path.dirname(__file__), "reports")
    os.makedirs(reports_dir, exist_ok=True)
    summary_path = os.path.join(reports_dir, "nl2sql_benchmark_results.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(benchmark_summary, f, indent=4)
        
    print(f"[PASS] Benchmark results written to {summary_path}")

if __name__ == "__main__":
    run_benchmarks()
