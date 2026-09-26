# nl2sql.py
# Clean Architecture: Use Case Layer
# Natural language -> SQL, with verification and repair of the generated query.
#
#   1. The generator proposes its best candidate; only if the analyzer rejects it are further
#      candidates generated (keeps the common case fast on CPU).
#   2. Each candidate is checked by the analyzer against the schema; the first valid one wins.
#   3. If none is valid, the top candidate is passed to the repair engine and the repaired
#      query is re-verified.

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
        k = num_candidates or self.num_candidates
        gen = self.generator.generate(question, schema, 1)
        pool = list(gen["candidates"])
        elapsed = gen["inference_time_ms"]
        checked = self._check(pool, schema)
        if k > 1 and not any(c["error_class"] == "CORRECT" for c in checked):
            more = self.generator.generate(question, schema, k)
            elapsed += more["inference_time_ms"]
            known = {c["sql"].lower() for c in pool}
            pool += [c for c in more["candidates"] if c["sql"].lower() not in known][:k - len(pool)]
            checked = self._check(pool, schema)

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
            "generation_time_ms": elapsed,
        }

    def _check(self, candidates, schema):
        out = []
        for rank, cand in enumerate(candidates):
            analysis = self.diagnosis.analyzer.analyze(cand["sql"], schema)
            out.append({**cand, "rank": rank + 1, "error_class": analysis.error_class,
                        "issues": [i.message for i in analysis.issues]})
        return out
