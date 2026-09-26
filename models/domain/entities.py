# entities.py
# Clean Architecture: Domain Layer
# Core business domain models. No dependencies on PyTorch, sqlglot or FastAPI here.

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional


@dataclass
class Issue:
    """A single problem found in a query."""
    error_class: str
    message: str
    token: Optional[str] = None          # offending identifier / token, when known
    source: str = "analyzer"             # "engine" (SQLite compiler), "static" (AST rule) or "policy"

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class AnalysisResult:
    """Deterministic verdict produced by the SQL analyzer."""
    error_class: str
    issues: List[Issue] = field(default_factory=list)
    engine_error: Optional[str] = None   # raw SQLite compiler message, if any
    schema_checked: bool = True          # False when no schema was available

    @property
    def is_error(self) -> bool:
        return self.error_class != "CORRECT"

    def to_dict(self) -> Dict:
        return {
            "error_class": self.error_class,
            "is_error": self.is_error,
            "issues": [i.to_dict() for i in self.issues],
            "engine_error": self.engine_error,
            "schema_checked": self.schema_checked,
        }


@dataclass
class ModelPrediction:
    """Output of the neural classifier."""
    error_class: str
    confidence: float
    probabilities: Dict[str, float]

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class Diagnosis:
    """Final answer for one query, fusing the analyzer and the model."""
    query: str
    error_class: str
    confidence: float
    decided_by: str                      # "analyzer", "model" or "analyzer+model"
    analysis: Optional[AnalysisResult] = None
    model: Optional[ModelPrediction] = None
    notes: List[str] = field(default_factory=list)

    @property
    def is_error(self) -> bool:
        return self.error_class != "CORRECT"

    def to_dict(self) -> Dict:
        return {
            "query": self.query,
            "is_error": self.is_error,
            "error_class": self.error_class,
            "confidence": self.confidence,
            "decided_by": self.decided_by,
            "analysis": self.analysis.to_dict() if self.analysis else None,
            "model": self.model.to_dict() if self.model else None,
            "notes": list(self.notes),
        }


@dataclass
class RepairStep:
    error_class: str
    description: str
    before: str
    after: str


@dataclass
class RepairResult:
    original_query: str
    repaired_query: Optional[str]
    success: bool                         # True when the repaired query passes the analyzer
    remaining_error: Optional[str]        # error class still present after repair (None if clean)
    steps: List[RepairStep] = field(default_factory=list)
    explanation: str = ""

    def to_dict(self) -> Dict:
        return {
            "original_query": self.original_query,
            "repaired_query": self.repaired_query,
            "success": self.success,
            "remaining_error": self.remaining_error,
            "steps": [asdict(s) for s in self.steps],
            "explanation": self.explanation,
        }
