import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.analyzer import SQLAnalyzer  # noqa: E402
from analysis.schema import DatabaseSchema  # noqa: E402

MUSIC = {
    "singer": {"columns": {"singer_id": "INTEGER", "name": "TEXT", "country": "TEXT", "age": "INTEGER"},
               "primary_keys": ["singer_id"]},
    "concert": {"columns": {"concert_id": "INTEGER", "concert_name": "TEXT", "stadium_id": "INTEGER", "year": "INTEGER"},
                "primary_keys": ["concert_id"],
                "foreign_keys": [{"column": "stadium_id", "target_table": "stadium", "target_column": "stadium_id"}]},
    "stadium": {"columns": {"stadium_id": "INTEGER", "name": "TEXT", "capacity": "INTEGER"},
                "primary_keys": ["stadium_id"]},
    "singer_in_concert": {"columns": {"concert_id": "INTEGER", "singer_id": "INTEGER"},
                          "primary_keys": ["concert_id", "singer_id"],
                          "foreign_keys": [{"column": "concert_id", "target_table": "concert", "target_column": "concert_id"},
                                           {"column": "singer_id", "target_table": "singer", "target_column": "singer_id"}]},
}


@pytest.fixture(scope="session")
def schema() -> DatabaseSchema:
    return DatabaseSchema.from_dict(MUSIC, "music")


@pytest.fixture(scope="session")
def analyzer() -> SQLAnalyzer:
    return SQLAnalyzer()


DATA_DIR = ROOT / "data" / "processed"
needs_data = pytest.mark.skipif(not (DATA_DIR / "test.jsonl").exists(),
                                reason="processed dataset missing (python -m data_pipeline.build_dataset)")
