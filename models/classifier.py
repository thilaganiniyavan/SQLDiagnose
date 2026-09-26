# classifier.py
# Clean Architecture: Interface Adapter
# Transformer sequence classifier for SQL errors (HuggingFace implementation of ISQLClassifier).
#
# Input format: the query and a compact serialisation of the schema are encoded as a text pair,
#   <s> SQL </s></s> table: col type, ... | table2: ... </s>
# truncating only the schema segment. Without the schema, table/column/type errors are not
# decidable from the text, so the schema is part of the model input by design.

import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from analysis.schema import DatabaseSchema
from .domain.entities import ModelPrediction
from .domain.interfaces import ISQLClassifier
from .domain.labels import MODEL_CLASSES

LABEL_FILE = "sqldiagnose_labels.json"


def schema_text(query: str, schema: Optional[DatabaseSchema]) -> str:
    return schema.serialize_for_model(query) if schema is not None and schema.tables else ""


class SQLErrorClassifier(ISQLClassifier):
    def __init__(self, model, tokenizer, labels: Sequence[str], max_length: int = 256, device: str = "cpu"):
        self.model = model
        self.tokenizer = tokenizer
        self.labels = list(labels)
        self.max_length = max_length
        self.device = torch.device(device)
        self.model.to(self.device)
        self.model.eval()

    # ------------------------------------------------------------------ construction
    @classmethod
    def from_base(cls, name_or_path: str, labels: Sequence[str] = MODEL_CLASSES, max_length: int = 256,
                  device: str = "cpu", dropout: Optional[float] = None) -> "SQLErrorClassifier":
        """A fresh classification head on top of a pretrained encoder (for training)."""
        kwargs = dict(num_labels=len(labels),
                      id2label={i: l for i, l in enumerate(labels)},
                      label2id={l: i for i, l in enumerate(labels)})
        if dropout is not None:
            kwargs.update(hidden_dropout_prob=dropout, attention_probs_dropout_prob=dropout)
        model = AutoModelForSequenceClassification.from_pretrained(name_or_path, **kwargs)
        tokenizer = AutoTokenizer.from_pretrained(name_or_path)
        return cls(model, tokenizer, labels, max_length, device)

    @classmethod
    def from_pretrained(cls, directory: str, device: str = "cpu") -> "SQLErrorClassifier":
        """Loads a fine-tuned checkpoint written by `save_pretrained`."""
        directory = Path(directory)
        meta = json.loads((directory / LABEL_FILE).read_text())
        model = AutoModelForSequenceClassification.from_pretrained(str(directory))
        tokenizer = AutoTokenizer.from_pretrained(str(directory))
        return cls(model, tokenizer, meta["labels"], meta.get("max_length", 256), device)

    def save_pretrained(self, directory: str, extra: Optional[Dict] = None) -> None:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        self.model.save_pretrained(str(directory))
        self.tokenizer.save_pretrained(str(directory))
        meta = {"labels": self.labels, "max_length": self.max_length, "input_format": "sql</s></s>schema"}
        meta.update(extra or {})
        (directory / LABEL_FILE).write_text(json.dumps(meta, indent=2))

    # ------------------------------------------------------------------ encoding
    def encode(self, queries: Sequence[str], schemas: Sequence[Optional[DatabaseSchema]],
               padding: bool = True) -> Dict[str, torch.Tensor]:
        texts = list(queries)
        pairs = [schema_text(q, s) for q, s in zip(queries, schemas)]
        return self.tokenizer(texts, pairs, truncation="only_second", max_length=self.max_length,
                              padding=padding, return_tensors="pt")

    # ------------------------------------------------------------------ inference
    @torch.no_grad()
    def predict_proba(self, queries: Sequence[str], schemas: Sequence[Optional[DatabaseSchema]],
                      batch_size: int = 32) -> List[List[float]]:
        out: List[List[float]] = []
        for i in range(0, len(queries), batch_size):
            enc = self.encode(queries[i:i + batch_size], schemas[i:i + batch_size])
            enc = {k: v.to(self.device) for k, v in enc.items()}
            logits = self.model(**enc).logits
            out.extend(torch.softmax(logits, dim=-1).cpu().tolist())
        return out

    def predict(self, query: str, schema: Optional[DatabaseSchema] = None) -> ModelPrediction:
        return self.predict_batch([query], [schema])[0]

    def predict_batch(self, queries: Sequence[str], schemas: Sequence[Optional[DatabaseSchema]],
                      batch_size: int = 32) -> List[ModelPrediction]:
        preds = []
        for probs in self.predict_proba(queries, schemas, batch_size):
            best = max(range(len(probs)), key=probs.__getitem__)
            preds.append(ModelPrediction(self.labels[best], float(probs[best]),
                                         {l: float(p) for l, p in zip(self.labels, probs)}))
        return preds

    def explain(self, query: str, schema: Optional[DatabaseSchema] = None, method: str = "gxi",
                steps: int = 16) -> Dict:
        """Token attributions for the predicted class ("gxi" = gradient x input, "ig" = integrated gradients)."""
        from evaluation.explainability import integrated_gradients
        enc = self.encode([query], [schema])
        return integrated_gradients(self.model, self.tokenizer, enc, self.labels, steps=steps,
                                    device=self.device, method=method)

    @property
    def backbone(self) -> str:
        return getattr(self.model.config, "_name_or_path", "unknown")

    def num_parameters(self) -> int:
        return sum(p.numel() for p in self.model.parameters())
