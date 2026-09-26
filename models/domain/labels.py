# labels.py
# Clean Architecture: Domain Layer
# Single source of truth for the SQL error taxonomy used by the analyzer, the
# classifier, the repair engine, the API and the UI.

from enum import IntEnum
from typing import Dict, List


class ErrorClass(IntEnum):
    CORRECT = 0
    SYNTAX_ERROR = 1
    UNKNOWN_TABLE = 2
    UNKNOWN_COLUMN = 3
    DATATYPE_MISMATCH = 4
    AMBIGUOUS_REFERENCE = 5
    PERMISSION_DENIED = 6
    SEMANTIC_ERROR = 7


CLASS_NAMES: List[str] = [c.name for c in ErrorClass]

CLASS_DESCRIPTIONS: Dict[str, str] = {
    "CORRECT": "No error detected.",
    "SYNTAX_ERROR": "The query violates SQL grammar (misspelled or missing keyword, comma, parenthesis, quote, operand).",
    "UNKNOWN_TABLE": "The query references a table that does not exist in the schema.",
    "UNKNOWN_COLUMN": "The query references a column that does not exist (or not in the referenced table).",
    "DATATYPE_MISMATCH": "Values or columns of incompatible types are compared or aggregated.",
    "AMBIGUOUS_REFERENCE": "A column or alias reference could resolve to more than one table.",
    "PERMISSION_DENIED": "The query touches a table or column that the access policy restricts.",
    "SEMANTIC_ERROR": "The query is grammatical but logically invalid (aggregate misuse, GROUP BY violations, "
                      "NULL comparison with '=', missing join condition, column-count mismatch, ...).",
}

# PERMISSION_DENIED cannot be inferred from query text, so it is decided by the
# access-policy check in the analyzer. The neural model is trained on the rest.
MODEL_CLASSES: List[str] = [n for n in CLASS_NAMES if n != "PERMISSION_DENIED"]

# When a query has several problems, the one reported as primary follows the
# order in which a database engine would reject it.
PRIORITY: List[str] = [
    "SYNTAX_ERROR",
    "UNKNOWN_TABLE",
    "UNKNOWN_COLUMN",
    "AMBIGUOUS_REFERENCE",
    "PERMISSION_DENIED",
    "DATATYPE_MISMATCH",
    "SEMANTIC_ERROR",
]
