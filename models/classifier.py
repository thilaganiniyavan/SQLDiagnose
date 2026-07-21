# classifier.py
# Clean Architecture: Interface Adapter
# Concrete implementation of the ISQLModel interface using HuggingFace & PyTorch.

import torch
import torch.nn as nn
from typing import Dict, List, Any
from pathlib import Path
from transformers import AutoModelForSequenceClassification, AutoConfig
from .domain.interfaces import ISQLModel
from evaluation.explainability import explain_query

class TransformerSQLClassifier(ISQLModel):
    """
    Adapter class wrapping HuggingFace AutoModelForSequenceClassification 
    to implement the domain model interface.
    """
    def __init__(self, model_name_or_path: str, num_labels: int, attention_dropout: float = None, hidden_dropout: float = None):
        self.model_name_or_path = model_name_or_path
        self.num_labels = num_labels
        
        try:
            config = AutoConfig.from_pretrained(model_name_or_path)
            if attention_dropout is not None:
                config.attention_probs_dropout_prob = attention_dropout
            if hidden_dropout is not None:
                config.hidden_dropout_prob = hidden_dropout
            config.num_labels = num_labels
        except Exception:
            config = None

        try:
            if config is not None:
                self.model = AutoModelForSequenceClassification.from_pretrained(
                    model_name_or_path,
                    config=config,
                    attn_implementation="eager"
                )
            else:
                self.model = AutoModelForSequenceClassification.from_pretrained(
                    model_name_or_path,
                    num_labels=num_labels,
                    attn_implementation="eager"
                )
        except Exception:
            if config is not None:
                self.model = AutoModelForSequenceClassification.from_pretrained(
                    model_name_or_path,
                    config=config
                )
            else:
                self.model = AutoModelForSequenceClassification.from_pretrained(
                    model_name_or_path,
                    num_labels=num_labels
                )

    def predict(self, tokenized_inputs: Dict[str, Any]) -> List[float]:
        """
        Runs model inference forward pass. Returns class probability scores.
        """
        self.model.eval()
        with torch.no_grad():
            # Move inputs to device matching model
            device = next(self.model.parameters()).device
            inputs = {k: v.to(device) if isinstance(v, torch.Tensor) else v for k, v in tokenized_inputs.items()}
            
            outputs = self.model(**inputs)
            logits = outputs.logits
            probs = torch.softmax(logits, dim=-1)
            return probs.squeeze(0).tolist()

    def predict_with_explanation(
        self,
        query: str,
        tokenizer: Any,
        target_class: int = None,
        save_dir: str = None
    ) -> Dict[str, Any]:
        """
        Executes inference and returns token attributions and attention weights.
        """
        save_path = Path(save_dir) if save_dir else None
        return explain_query(
            model=self.model,
            tokenizer=tokenizer,
            query=query,
            target_class=target_class,
            save_dir=save_path
        )

    def save_pretrained(self, save_directory: str) -> None:
        """
        Delegates weight saving to underlying HuggingFace save_pretrained.
        """
        self.model.save_pretrained(save_directory)

    def load_pretrained(self, model_directory: str) -> None:
        """
        Loads the HuggingFace model weights.
        """
        try:
            self.model = AutoModelForSequenceClassification.from_pretrained(
                model_directory,
                num_labels=self.num_labels,
                attn_implementation="eager"
            )
        except Exception:
            self.model = AutoModelForSequenceClassification.from_pretrained(
                model_directory,
                num_labels=self.num_labels
            )
