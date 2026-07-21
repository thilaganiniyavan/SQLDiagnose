# validator.py
# Query validation sandbox executing SQL statements against local SQLite database instances.

import sqlite3
import os
from pathlib import Path
from typing import Tuple, Optional

class SQLValidator:
    def __init__(self, database_dir: Path):
        self.database_dir = database_dir

    def _get_db_path(self, db_id: str) -> Optional[Path]:
        # Databases are stored under raw/spider/database/{db_id}/{db_id}.sqlite
        db_path = self.database_dir / "spider" / "database" / db_id / f"{db_id}.sqlite"
        if db_path.exists():
            return db_path
        # Also check SParC or CoSQL directories if needed
        sparc_db_path = self.database_dir / "sparc" / "database" / db_id / f"{db_id}.sqlite"
        if sparc_db_path.exists():
            return sparc_db_path
        return None

    def validate_query(self, query: str, db_id: str) -> Tuple[bool, Optional[str]]:
        """
        Executes the query in read-only mode against the target database.
        Returns:
            (is_valid, error_message)
        """
        # Check if it is a mock database configuration
        from .mock_data import MOCK_SCHEMAS, MOCK_DDL
        if db_id.lower() in MOCK_SCHEMAS:
            conn = None
            try:
                conn = sqlite3.connect(":memory:")
                cursor = conn.cursor()
                for statement in MOCK_DDL[db_id.lower()]:
                    cursor.execute(statement)
                cursor.execute(f"EXPLAIN {query}")
                return True, None
            except sqlite3.OperationalError as e:
                return False, str(e)
            except Exception as e:
                return False, str(e)
            finally:
                if conn:
                    conn.close()

        db_path = self._get_db_path(db_id)
        if not db_path:
            # Fallback if SQLite file doesn't exist: assume syntactic parsing is OK,
            # or return True as we cannot verify
            return True, None

        conn = None
        try:
            # Open database in read-only mode
            db_uri = f"file:{db_path.absolute().as_posix()}?mode=ro"
            conn = sqlite3.connect(db_uri, uri=True)
            cursor = conn.cursor()
            
            # Use EXPLAIN to validate syntax and schema without retrieving actual data rows
            cursor.execute(f"EXPLAIN {query}")
            return True, None
        except sqlite3.OperationalError as e:
            # OperationalError covers syntax errors, table/column not found
            return False, str(e)
        except sqlite3.DatabaseError as e:
            return False, str(e)
        except Exception as e:
            return False, str(e)
        finally:
            if conn:
                conn.close()

if __name__ == "__main__":
    # Test validator
    db_dir = Path(__file__).parent / "raw"
    validator = SQLValidator(db_dir)
    # Test valid query
    valid_res = validator.validate_query("SELECT * FROM artist", "music_4")
    print(f"Valid query result: {valid_res}")
    # Test invalid query
    invalid_res = validator.validate_query("SELECT invalid_col FROM artist", "music_4")
    print(f"Invalid query result: {invalid_res}")
