# interfaces.py
# Clean Architecture: Domain Layer
# Abstract contracts that the use cases (services/) depend on.

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Sequence

from .entities import ModelPrediction


class ISQLClassifier(ABC):
    """A learned classifier mapping (query, schema) to an error class distribution."""

    @abstractmethod
    def predict(self, query: str, schema: Optional[Any] = None) -> ModelPrediction:
        ...

    @abstractmethod
    def predict_batch(self, queries: Sequence[str], schemas: Sequence[Optional[Any]]) -> List[ModelPrediction]:
        ...

    @abstractmethod
    def save_pretrained(self, directory: str, extra: Optional[Dict] = None) -> None:
        ...


class ISQLGenerator(ABC):
    """Natural language to SQL generator."""

    @abstractmethod
    def generate(self, question: str, schema: Any, num_candidates: int = 1) -> Dict[str, Any]:
        ...
