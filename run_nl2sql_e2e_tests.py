# run_nl2sql_e2e_tests.py
# Clean Architecture: Frameworks & Drivers
# End-to-End pipeline testing verifying NL -> SQL -> Validation -> Repair

import os
import torch
import json
from pathlib import Path
from models.generator import SQLGeneratorService
from models.classifier import TransformerSQLClassifier
from repair.repair_engine import SQLRepairEngine
from transformers import AutoTokenizer

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

TEST_QUESTIONS = [
    {
        "question": "List all department names",
        "description": "Selection test"
    },
    {
        "question": "Find names of employees earning more than 50000",
        "description": "Filtering test"
    },
    {
        "question": "Get the maximum budget across all departments",
        "description": "Aggregation test"
    },
    {
        "question": "Show department IDs and total salary for each department",
        "description": "Group By test"
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

def run_e2e_pipeline():
    print("=== STARTING NL2SQL END-TO-END PIPELINE VALIDATION ===")
    
    # 1. Initialize all three modules
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Initializing modules on device: {device} ...")
    
    generator = SQLGeneratorService(device=device)
    
    checkpoint_path = Path("experiments/exp_claudios_codebert-base_42/checkpoints/checkpoint_best.pt")
    
    if checkpoint_path.exists():
        print(f"Loading custom state dict checkpoint from: {checkpoint_path}")
        base_model_name = "claudios/codebert-base"
        try:
            tokenizer = AutoTokenizer.from_pretrained(base_model_name)
            classifier = TransformerSQLClassifier(model_name_or_path=base_model_name, num_labels=8)
            state = torch.load(checkpoint_path, map_location="cpu")
            classifier.model.load_state_dict(state["model_state_dict"])
            print("Successfully loaded fine-tuned model weights.")
        except Exception as e:
            print(f"Failed to load fine-tuned checkpoint: {e}. Falling back to roberta-base...")
            tokenizer = AutoTokenizer.from_pretrained("roberta-base")
            classifier = TransformerSQLClassifier(model_name_or_path="roberta-base", num_labels=8)
    else:
        print("Fine-tuned checkpoint not found. Using base roberta-base...")
        tokenizer = AutoTokenizer.from_pretrained("roberta-base")
        classifier = TransformerSQLClassifier(model_name_or_path="roberta-base", num_labels=8)
        
    classifier.model.to(device)
    classifier.model.eval()
    repair_engine = SQLRepairEngine()
    
    print("\nExecuting End-to-End Pipeline Pipeline Tests...")
    print("-"*70)
    
    pipeline_runs = []
    
    for case in TEST_QUESTIONS:
        question = case["question"]
        desc = case["description"]
        print(f"\n[PIPELINE TEST - {desc}]")
        print(f"NL Question: '{question}'")
        
        # Step 1: Text-to-SQL generation
        gen_res = generator.generate_sql(question, SCHEMA)
        generated_sql = gen_res["generated_sql"]
        gen_conf = gen_res["confidence"]
        print(f"1. Generated SQL: {generated_sql} (Confidence: {gen_conf*100:.1f}%)")
        
        # Step 2: Classifier validation
        inputs = tokenizer(generated_sql, return_tensors="pt")
        tokenized_inputs = {k: v.to(device) if isinstance(v, torch.Tensor) else v for k, v in inputs.items()}
        
        with torch.no_grad():
            probs = classifier.predict(tokenized_inputs)
            
        pred_idx = int(torch.argmax(torch.tensor(probs)).item())
        pred_class = CLASS_NAMES[pred_idx]
        val_conf = float(probs[pred_idx])
        is_error = (pred_idx != 0)
        
        print(f"2. Validation Category: {pred_class} (Confidence: {val_conf*100:.1f}%)")
        
        # Step 3: Repair Engine if error detected
        repaired_sql = None
        suggested_fix = None
        explanation = None
        
        if is_error:
            print("  --> Error detected! Invoking Repair Engine...")
            rep_res = repair_engine.repair(
                query=generated_sql,
                predicted_class=pred_idx,
                confidence=val_conf,
                schema=SCHEMA
            )
            repaired_sql = rep_res["corrected_query"]
            suggested_fix = rep_res["suggested_correction"]
            explanation = rep_res["explanation"]
            
            print(f"3. Repaired SQL: {repaired_sql}")
            print(f"   Explanation: {explanation}")
            print(f"   Suggested Fix: {suggested_fix}")
        else:
            print("3. Repaired SQL: Not required (Query is CORRECT)")
            
        pipeline_runs.append({
            "question": question,
            "generated_sql": generated_sql,
            "generated_confidence": gen_conf,
            "predicted_class": pred_class,
            "validation_confidence": val_conf,
            "repaired_sql": repaired_sql,
            "suggested_fix": suggested_fix
        })
        print("-"*70)
        
    # Write summary pipeline results
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)
    summary_path = reports_dir / "nl2sql_pipeline_runs.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(pipeline_runs, f, indent=4)
    print(f"\n[PASS] E2E Pipeline run results written to {summary_path}")

if __name__ == "__main__":
    run_e2e_pipeline()
