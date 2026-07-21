# predictor.py
# Clean Architecture: Interface Adapter
# Predictor class performing single and batch inference using trained adapters.

import torch
from typing import Dict, List, Any, Union
from models.classifier import TransformerSQLClassifier
from models.tokenizer import TransformerSQLTokenizer
from models.domain.entities import SQLQuery, ClassificationResult

class SQLQueryPredictor:
    def __init__(self, model_dir: str, backbone: str, num_labels: int, classes: Dict[int, str]):
        self.tokenizer = TransformerSQLTokenizer(backbone)
        self.model = TransformerSQLClassifier(backbone, num_labels)
        self.model.load_pretrained(model_dir)
        self.classes = classes
        
    def predict_query(self, query_text: str, max_length: int = 256) -> ClassificationResult:
        """
        Predicts classification label for a single query text.
        """
        tokenized = self.tokenizer.encode(query_text, max_length=max_length)
        probs = self.model.predict(tokenized)
        
        pred_idx = int(torch.tensor(probs).argmax().item())
        pred_label = self.classes.get(pred_idx, "UNKNOWN")
        confidence = probs[pred_idx]
        
        all_probs_dict = {self.classes.get(idx, f"CLASS_{idx}"): float(p) for idx, p in enumerate(probs)}
        
        domain_query = SQLQuery(raw_query=query_text)
        return ClassificationResult(
            query=domain_query,
            error_class_id=pred_idx,
            error_class_name=pred_label,
            confidence=confidence,
            all_probabilities=all_probs_dict
        )

    def predict_batch(self, queries: List[str], max_length: int = 256) -> List[ClassificationResult]:
        """
        Predicts classification labels for a batch of query texts.
        """
        return [self.predict_query(q, max_length) for q in queries]
