# entities.py
# Clean Architecture: Domain Layer
# Core business domain models. Absolutely no dependencies on PyTorch or FastAPI here.

from dataclasses import dataclass
from typing import Dict, Optional

@dataclass
class SQLQuery:
    """
    Core Domain object representing an SQL query string to be analyzed.
    """
    raw_query: str
    db_dialect: Optional[str] = "postgres"


@dataclass
class ClassificationResult:
    """
    Core Domain object representing the multi-class prediction outcomes.
    """
    query: SQLQuery
    error_class_id: int
    error_class_name: str
    confidence: float
    all_probabilities: Dict[str, float]
