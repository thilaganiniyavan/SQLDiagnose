# diagnosis.py
# Clean Architecture: Use Case Layer
# Orchestrates the deterministic analyzer, the neural classifier and the repair engine.
#
# Decision rule
#   * The analyzer is authoritative for every error it detects (it compiles the query against the
#     schema and applies explicit rules), so its verdict wins whenever it reports a problem.
#   * If the analyzer finds no problem and a schema was supplied, the query is CORRECT; a confident
#     dissenting model prediction is surfaced as a note, not as the verdict.
#   * Without a schema the analyzer can only check grammar and schema-independent semantics; if it
#     finds nothing, the model's prediction is used when it is confident, flagged as unverified.

from typing import List, Optional, Sequence

from analysis.analyzer import SQLAnalyzer
from analysis.schema import DatabaseSchema
from models.domain.entities import Diagnosis, ModelPrediction, RepairResult
from models.domain.interfaces import ISQLClassifier
from repair.repair_engine import SQLRepairEngine


class DiagnosisService:
    def __init__(self, classifier: Optional[ISQLClassifier] = None, analyzer: Optional[SQLAnalyzer] = None,
                 repair_engine: Optional[SQLRepairEngine] = None, model_threshold: float = 0.8):
        self.classifier = classifier
        self.analyzer = analyzer or SQLAnalyzer()
        self.repair_engine = repair_engine or SQLRepairEngine(self.analyzer)
        self.model_threshold = model_threshold

    @property
    def model_loaded(self) -> bool:
        return self.classifier is not None

    def diagnose(self, query: str, schema: Optional[DatabaseSchema] = None, use_model: bool = True) -> Diagnosis:
        return self.diagnose_batch([query], [schema], use_model)[0]

    def diagnose_batch(self, queries: Sequence[str], schemas: Sequence[Optional[DatabaseSchema]],
                       use_model: bool = True) -> List[Diagnosis]:
        analyses = [self.analyzer.analyze(q, s) for q, s in zip(queries, schemas)]
        preds: List[Optional[ModelPrediction]] = [None] * len(queries)
        if use_model and self.classifier is not None and queries:
            preds = self.classifier.predict_batch(list(queries), list(schemas))
        return [self._fuse(q, a, p) for q, a, p in zip(queries, analyses, preds)]

    def _fuse(self, query, analysis, pred: Optional[ModelPrediction]) -> Diagnosis:
        notes: List[str] = []
        if analysis.is_error:
            agree = pred is not None and pred.error_class == analysis.error_class
            if pred is not None and not agree and analysis.error_class != "PERMISSION_DENIED":
                notes.append(f"The model predicted {pred.error_class} ({pred.confidence:.0%}); "
                             f"the analyzer's verified finding takes precedence.")
            return Diagnosis(query, analysis.error_class, 1.0, "analyzer+model" if agree else "analyzer",
                             analysis, pred, notes)

        if analysis.schema_checked:
            if pred is not None and pred.error_class != "CORRECT" and pred.confidence >= self.model_threshold:
                notes.append(f"The model suspects {pred.error_class} ({pred.confidence:.0%}), but the query "
                             f"compiles against the schema and passes every rule; review it if the result looks wrong.")
            agree = pred is not None and pred.error_class == "CORRECT"
            return Diagnosis(query, "CORRECT", 1.0, "analyzer+model" if agree else "analyzer", analysis, pred, notes)

        notes.append("No schema was provided, so table/column/type checks were not possible.")
        if pred is not None and pred.error_class != "CORRECT" and pred.confidence >= self.model_threshold:
            notes.append("This verdict comes from the model alone and is unverified.")
            return Diagnosis(query, pred.error_class, pred.confidence, "model", analysis, pred, notes)
        return Diagnosis(query, "CORRECT", pred.probabilities.get("CORRECT", 1.0) if pred else 1.0,
                         "analyzer", analysis, pred, notes)

    def repair(self, query: str, schema: Optional[DatabaseSchema] = None) -> RepairResult:
        return self.repair_engine.repair(query, schema)

    def explain(self, query: str, schema: Optional[DatabaseSchema] = None, method: str = "gxi"):
        if self.classifier is None:
            return None
        return self.classifier.explain(query, schema, method=method)
