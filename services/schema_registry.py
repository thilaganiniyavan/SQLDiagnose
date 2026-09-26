# schema_registry.py
# Named example schemas (the Spider databases used by the dataset) plus request-supplied schemas.

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from analysis.schema import DatabaseSchema

DEFAULT_SCHEMAS = Path(__file__).resolve().parents[1] / "data" / "processed" / "schemas.json"


class SchemaRegistry:
    def __init__(self, path: Path = DEFAULT_SCHEMAS):
        self._raw: Dict[str, Dict] = json.loads(path.read_text()) if path.exists() else {}
        self._cache: Dict[str, DatabaseSchema] = {}

    def names(self) -> List[str]:
        return sorted(self._raw)

    def get(self, db_id: str) -> Optional[DatabaseSchema]:
        if db_id not in self._raw:
            return None
        if db_id not in self._cache:
            self._cache[db_id] = DatabaseSchema.from_dict(self._raw[db_id], db_id)
        return self._cache[db_id]

    def raw(self, db_id: str) -> Optional[Dict]:
        return self._raw.get(db_id)

    def resolve(self, schema: Optional[Dict[str, Any]] = None, db_id: Optional[str] = None,
                access_policy: Optional[Dict[str, Any]] = None) -> Optional[DatabaseSchema]:
        """An explicit schema wins over a named one; an access policy is attached to either."""
        if schema:
            return DatabaseSchema.from_dict(schema, "request", access_policy)
        if db_id:
            base = self.get(db_id)
            if base is None:
                raise KeyError(db_id)
            return base.with_policy(access_policy) if access_policy else base
        return None
