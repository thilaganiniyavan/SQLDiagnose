# tokenizer.py
# Clean Architecture: Interface Adapter
# Concrete implementation of the ISQLTokenizer interface using HuggingFace Tokenizers.

from typing import Dict, List, Any
from .domain.interfaces import ISQLTokenizer
from transformers import AutoTokenizer

class TransformerSQLTokenizer(ISQLTokenizer):
    """
    Adapter class wrapping HuggingFace AutoTokenizer to implement 
    the domain tokenizer interface.
    """
    def __init__(self, model_name_or_path: str):
        self.model_name_or_path = model_name_or_path
        self.tokenizer = AutoTokenizer.from_pretrained(model_name_or_path)

    def encode(self, text: str, max_length: int) -> Dict[str, Any]:
        """
        Tokenizes SQL text, adding special tokens, padding, truncation, 
        and returning PyTorch compatible tensors.
        """
        encoding = self.tokenizer(
            text,
            add_special_tokens=True,
            max_length=max_length,
            padding="max_length",
            truncation=True,
            return_attention_mask=True,
            return_tensors="pt"
        )
        return {
            "input_ids": encoding["input_ids"],
            "attention_mask": encoding["attention_mask"]
        }

    def decode(self, token_ids: List[int]) -> str:
        """
        Translates token IDs back to a readable SQL string.
        """
        return self.tokenizer.decode(token_ids, skip_special_tokens=True)
