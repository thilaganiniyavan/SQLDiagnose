import sys
import os
from pathlib import Path
import json
import time
import torch
import pandas as pd
from sklearn.metrics import classification_report, matthews_corrcoef, cohen_kappa_score

# Add project root to path and handle HF datasets conflict
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import datasets as local_datasets
original_local_datasets = sys.modules.get("datasets")
if "datasets" in sys.modules:
    del sys.modules["datasets"]

parent_dir = os.path.abspath(str(project_root))
original_sys_path = list(sys.path)
sys.path = [p for p in sys.path if os.path.abspath(p) != parent_dir]

import datasets as hf_datasets

sys.path = original_sys_path
if original_local_datasets:
    sys.modules["datasets"] = original_local_datasets

from models.model_factory import SQLModelFactory
from models.tokenizer_factory import SQLTokenizerFactory
from datasets.dataloader import SQLClassificationDataset

def evaluate_checkpoint(checkpoint_path: Path, df_test: pd.DataFrame, tokenizer, max_len=256, device="cuda") -> dict:
    print(f"Evaluating checkpoint: {checkpoint_path.name}")
    
    # Load model configuration & weights
    model_factory = SQLModelFactory()
    model = model_factory.get_model(
        model_name_or_path="claudios/codebert-base",
        num_labels=8
    )
    
    # Load weights
    state = torch.load(checkpoint_path, map_location="cpu")
    model.model.load_state_dict(state["model_state_dict"])
    model.model.to(device)
    model.model.eval()
    
    # Setup dataset & loader
    queries = df_test["sql_query"].tolist()
    labels = df_test["label"].tolist()
    
    dataset = SQLClassificationDataset(queries, labels, tokenizer.tokenizer, max_len)
    loader = torch.utils.data.DataLoader(dataset, batch_size=32, shuffle=False)
    
    y_true = []
    y_pred = []
    
    # Benchmark latency (run 100 sequential queries)
    latency_queries = queries[:100]
    latencies = []
    with torch.no_grad():
        for q in latency_queries:
            inputs = tokenizer.tokenizer(
                q,
                max_length=max_len,
                padding="max_length",
                truncation=True,
                return_tensors="pt"
            )
            inputs = {k: v.to(device) for k, v in inputs.items()}
            
            # Warmup & time it
            start = time.perf_counter()
            outputs = model.model(**inputs)
            latencies.append(time.perf_counter() - start)
            
    avg_latency_ms = (sum(latencies) / len(latencies)) * 1000.0
    
    # Run complete test set evaluation
    with torch.no_grad():
        for batch in loader:
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            batch_labels = batch["labels"].to(device)
            
            outputs = model.model(input_ids=input_ids, attention_mask=attention_mask)
            preds = torch.argmax(outputs.logits, dim=-1)
            
            y_true.extend(batch_labels.cpu().tolist())
            y_pred.extend(preds.cpu().tolist())
            
    # Compute metrics
    report = classification_report(y_true, y_pred, output_dict=True, zero_division=0)
    acc = report["accuracy"]
    macro_f1 = report["macro avg"]["f1-score"]
    
    mcc = matthews_corrcoef(y_true, y_pred)
    kappa = cohen_kappa_score(y_true, y_pred)
    
    model_size_mb = os.path.getsize(checkpoint_path) / (1024 * 1024)
    
    # Per-class precision/recall/f1
    per_class = {}
    for label_str, metrics in report.items():
        if label_str.isdigit():
            per_class[label_str] = {
                "precision": metrics["precision"],
                "recall": metrics["recall"],
                "f1-score": metrics["f1-score"],
                "support": metrics["support"]
            }
            
    return {
        "accuracy": acc,
        "macro_f1": macro_f1,
        "mcc": mcc,
        "cohen_kappa": kappa,
        "latency_ms": avg_latency_ms,
        "model_size_mb": model_size_mb,
        "per_class": per_class
    }

def main():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Using device: {device}")
    
    processed_dir = project_root / "datasets" / "processed"
    df_test = pd.read_csv(processed_dir / "dataset_test.csv")
    
    # Map error type to integers
    class_mapping = {
        "MISSING_COMMA": 1,
        "MISSING_FROM": 1,
        "PARENTHESES_MISMATCH": 1,
        "RESERVED_KEYWORD_MISUSE": 1,
        "INCORRECT_WHERE": 1,
        "UNKNOWN_TABLE": 2,
        "UNKNOWN_COLUMN": 3,
        "DATATYPE_MISMATCH": 4,
        "DUPLICATE_ALIAS": 5,
        "PERMISSION_DENIED": 6,
        "WRONG_JOIN": 7,
        "MISSING_JOIN_CONDITION": 7,
        "WRONG_GROUPBY": 7,
        "AGGREGATE_MISUSE": 7,
        "WRONG_ALIAS": 7,
        "HAVING_MISUSE": 7,
        "ORDERBY_MISUSE": 7,
        "LIMIT_MISUSE": 7,
        "NESTED_QUERY_MISTAKE": 7,
        "FUNCTION_MISUSE": 7,
        "NULL_COMPARISON_ERRORS": 7,
        "CORRECT": 0
    }
    df_test["label"] = df_test["error_type"].map(class_mapping)
    
    tokenizer_factory = SQLTokenizerFactory()
    tokenizer = tokenizer_factory.get_tokenizer("claudios/codebert-base")
    
    exp_dir = project_root / "experiments" / "exp_claudios_codebert-base_42"
    
    legacy_ckpt = exp_dir / "checkpoints_legacy" / "checkpoint_best.pt"
    opt_ckpt = exp_dir / "checkpoints" / "checkpoint_best.pt"
    
    if not legacy_ckpt.exists():
        print(f"Legacy checkpoint not found at: {legacy_ckpt}. Using standard checkpoint if legacy doesn't exist.")
        # Try checkpoints_orig or checkpoints
        if (exp_dir / "checkpoints_orig" / "checkpoint_best.pt").exists():
            legacy_ckpt = exp_dir / "checkpoints_orig" / "checkpoint_best.pt"
            
    results = {}
    
    if legacy_ckpt.exists():
        results["original"] = evaluate_checkpoint(legacy_ckpt, df_test, tokenizer, device=device)
    else:
        print("Warning: Could not locate original baseline checkpoint. Skipping original evaluation.")
        
    if opt_ckpt.exists():
        results["optimized"] = evaluate_checkpoint(opt_ckpt, df_test, tokenizer, device=device)
    else:
        print(f"Error: Optimized checkpoint not found at: {opt_ckpt}")
        sys.exit(1)
        
    # Save comparison report
    comp_path = project_root / "experiments" / "final_model_comparison.json"
    with open(comp_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"Model comparison saved to {comp_path}")
    
    # Print comparison table
    print("\n" + "="*80)
    print(f"{'Metric':<30} | {'Original Model':<18} | {'Optimized Model':<18}")
    print("-"*80)
    
    metrics_list = [
        ("accuracy", "Accuracy", "{:.2%}"),
        ("macro_f1", "Macro F1", "{:.2%}"),
        ("mcc", "Matthews Corr (MCC)", "{:.4f}"),
        ("cohen_kappa", "Cohen's Kappa", "{:.4f}"),
        ("latency_ms", "Inference Latency (ms)", "{:.2f} ms"),
        ("model_size_mb", "Model Size (MB)", "{:.1f} MB")
    ]
    
    for key, name, fmt in metrics_list:
        orig_val = results["original"].get(key, 0.0) if "original" in results else 0.0
        opt_val = results["optimized"].get(key, 0.0)
        print(f"{name:<30} | {fmt.format(orig_val):<18} | {fmt.format(opt_val):<18}")
    print("="*80)

if __name__ == "__main__":
    main()
