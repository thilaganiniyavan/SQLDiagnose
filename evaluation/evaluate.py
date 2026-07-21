# evaluate.py
# Clean Architecture: Use Case Layer
# Main orchestrator for evaluation pipelines.

import torch
import numpy as np
from pathlib import Path
from typing import Dict, List, Any
from .metrics import (
    compute_classification_report,
    plot_confusion_matrix,
    plot_roc_curves,
    plot_pr_curves,
    plot_calibration_curves
)

class ModelEvaluator:
    """
    Computes validation and test metrics from model predictions.
    Saves validation performance reports.
    """
    def __init__(self, model, test_loader, device: str):
        self.model = model
        self.test_loader = test_loader
        self.device = device

    def run_evaluation(self) -> Dict[str, Any]:
        """
        Runs evaluation over the target dataset. 
        Returns classification dictionaries (F1, Precision, Recall).
        """
        self.model.model.eval()
        
        y_true = []
        y_pred = []
        y_probs = []
        y_queries = []
        
        with torch.no_grad():
            for batch in self.test_loader:
                input_ids = batch["input_ids"].to(self.device)
                attention_mask = batch["attention_mask"].to(self.device)
                labels = batch["labels"].to(self.device)
                queries = batch["query"]
                
                outputs = self.model.model(input_ids=input_ids, attention_mask=attention_mask)
                logits = outputs.logits
                
                probs = torch.softmax(logits, dim=-1)
                preds = torch.argmax(logits, dim=-1)
                
                y_true.extend(labels.cpu().tolist())
                y_pred.extend(preds.cpu().tolist())
                y_probs.extend(probs.cpu().tolist())
                y_queries.extend(queries)
                
        metrics_dict = compute_classification_report(y_true, y_pred, y_probs)
        return {
            "y_true": y_true,
            "y_pred": y_pred,
            "y_probs": y_probs,
            "y_queries": y_queries,
            "metrics": metrics_dict
        }

def run_evaluation_pipeline(
    model, test_loader, device: str, classes: List[str], report_dir: Path
) -> Dict[str, Any]:
    """
    Evaluates a pretrained checkpoint and generates all validation reports and figures.
    """
    report_dir.mkdir(parents=True, exist_ok=True)
    
    evaluator = ModelEvaluator(model, test_loader, device)
    eval_results = evaluator.run_evaluation()
    
    y_true = eval_results["y_true"]
    y_pred = eval_results["y_pred"]
    y_probs = eval_results["y_probs"]
    y_queries = eval_results["y_queries"]
    
    # Save statistics and figures
    plot_confusion_matrix(y_true, y_pred, classes, str(report_dir / "confusion_matrix.png"))
    plot_roc_curves(y_true, y_probs, classes, str(report_dir / "roc_curves.png"))
    plot_pr_curves(y_true, y_probs, classes, str(report_dir / "pr_curves.png"))
    plot_calibration_curves(y_true, y_probs, classes, str(report_dir / "calibration_curves.png"))
    
    # Export metrics json
    metrics_path = report_dir.parent / "metrics" / "eval_metrics.json"
    with open(metrics_path, "w", encoding="utf-8") as f:
        import json
        json.dump(eval_results["metrics"], f, indent=2)
        
    # Export predictions json
    predictions_path = report_dir.parent / "metrics" / "predictions.json"
    predictions = []
    for q, t, p, probs in zip(y_queries, y_true, y_pred, y_probs):
        predictions.append({
            "query": q,
            "true_label": t,
            "pred_label": p,
            "probabilities": probs
        })
    with open(predictions_path, "w", encoding="utf-8") as f:
        json.dump(predictions, f, indent=2)
        
    return eval_results
