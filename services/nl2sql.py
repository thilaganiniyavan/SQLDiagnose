# nl2sql.py
# Clean Architecture: Use Case Layer
# Natural language -> SQL, with verification and repair of the generated query.
#
#   1. The generator proposes several candidates (beam search).
#   2. Each candidate is checked by the analyzer against the schema; the first valid one wins.
#   3. If none is valid, the most confident candidate is passed to the repair engine and the
#      repaired query is re-verified.

from typing import Any, Dict, Optional

from analysis.schema import DatabaseSchema
from models.domain.interfaces import ISQLGenerator
from .diagnosis import DiagnosisService


class NL2SQLService:
    def __init__(self, generator: ISQLGenerator, diagnosis: DiagnosisService, num_candidates: int = 3):
        self.generator = generator
        self.diagnosis = diagnosis
        self.num_candidates = num_candidates

    def run(self, question: str, schema: DatabaseSchema, num_candidates: Optional[int] = None) -> Dict[str, Any]:
        gen = self.generator.generate(question, schema, num_candidates or self.num_candidates)
        checked = []
        for rank, cand in enumerate(gen["candidates"]):
            analysis = self.diagnosis.analyzer.analyze(cand["sql"], schema)
            checked.append({**cand, "rank": rank + 1, "error_class": analysis.error_class,
                            "issues": [i.message for i in analysis.issues]})

        chosen = next((c for c in checked if c["error_class"] == "CORRECT"), None)
        repair = None
        if chosen is not None:
            final_sql, status = chosen["sql"], ("valid" if chosen["rank"] == 1 else "valid_alternative")
        elif checked:
            repair = self.diagnosis.repair(checked[0]["sql"], schema)
            final_sql = repair.repaired_query if repair.success else checked[0]["sql"]
            status = "repaired" if repair.success else "invalid"
        else:
            final_sql, status = None, "no_candidate"

        diagnosis = self.diagnosis.diagnose(final_sql, schema) if final_sql else None
        return {
            "question": question,
            "sql": final_sql,
            "status": status,
            "candidates": checked,
            "repair": repair.to_dict() if repair else None,
            "diagnosis": diagnosis.to_dict() if diagnosis else None,
            "generator": gen["model"],
            "prompt_truncated": gen["prompt_truncated"],
            "generation_time_ms": gen["inference_time_ms"],
        }
