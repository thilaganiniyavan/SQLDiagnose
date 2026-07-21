# schema_resolver.py
# Resolves database schemas across different source datasets into a unified dict layout.

import json
from pathlib import Path
from typing import Dict, Any, List

class SchemaResolver:
    def __init__(self, raw_dir: Path):
        self.raw_dir = raw_dir
        self.schemas: Dict[str, Dict[str, Any]] = {}
        self._load_spider_schemas()
        self._load_bird_schemas()
        self._load_wikisql_schemas()
        
        # Load mock schemas for fallback
        from .mock_data import MOCK_SCHEMAS
        for db_id, s in MOCK_SCHEMAS.items():
            self.schemas[db_id.lower()] = s

    def _load_spider_schemas(self):
        # Spider, SParC, and CoSQL share the same databases and tables.json format
        spider_tables = self.raw_dir / "spider" / "tables.json"
        if not spider_tables.exists():
            return
            
        with open(spider_tables, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        for db_info in data:
            db_id = db_info["db_id"]
            tables = db_info["table_names_original"]
            columns = db_info["column_names_original"]  # Contains [table_index, column_name]
            col_types = db_info["column_types"]
            
            db_schema = {}
            for t_idx, t_name in enumerate(tables):
                db_schema[t_name.lower()] = {
                    "columns": {},
                    "primary_keys": [],
                    "foreign_keys": []
                }
                
            for col_idx, (t_idx, col_name) in enumerate(columns):
                if t_idx == -1:
                    continue  # wildcard * column
                t_name = tables[t_idx].lower()
                col_type = col_types[col_idx].upper()
                db_schema[t_name]["columns"][col_name.lower()] = col_type
                
            # Primary keys
            pks = db_info["primary_keys"]
            for pk_col_idx in pks:
                t_idx, col_name = columns[pk_col_idx]
                if t_idx != -1:
                    db_schema[tables[t_idx].lower()]["primary_keys"].append(col_name.lower())
                    
            # Foreign keys
            fks = db_info["foreign_keys"]
            for src_idx, tgt_idx in fks:
                src_t_idx, src_col = columns[src_idx]
                tgt_t_idx, tgt_col = columns[tgt_idx]
                if src_t_idx != -1 and tgt_t_idx != -1:
                    db_schema[tables[src_t_idx].lower()]["foreign_keys"].append({
                        "column": src_col.lower(),
                        "target_table": tables[tgt_t_idx].lower(),
                        "target_column": tgt_col.lower()
                    })
                    
            self.schemas[db_id.lower()] = db_schema

    def _load_bird_schemas(self):
        bird_tables = self.raw_dir / "bird" / "dev_tables.json"
        if not bird_tables.exists():
            return
            
        with open(bird_tables, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        for db_info in data:
            db_id = db_info["db_id"]
            tables = db_info["table_names_original"]
            columns = db_info["column_names_original"]
            col_types = db_info["column_types"]
            
            db_schema = {}
            for t_idx, t_name in enumerate(tables):
                db_schema[t_name.lower()] = {
                    "columns": {},
                    "primary_keys": [],
                    "foreign_keys": []
                }
                
            for col_idx, (t_idx, col_name) in enumerate(columns):
                if t_idx == -1:
                    continue
                t_name = tables[t_idx].lower()
                col_type = col_types[col_idx].upper()
                db_schema[t_name]["columns"][col_name.lower()] = col_type
                
            pks = db_info.get("primary_keys", [])
            for pk_col_idx in pks:
                if pk_col_idx < len(columns):
                    t_idx, col_name = columns[pk_col_idx]
                    if t_idx != -1:
                        db_schema[tables[t_idx].lower()]["primary_keys"].append(col_name.lower())
                        
            fks = db_info.get("foreign_keys", [])
            for src_idx, tgt_idx in fks:
                if src_idx < len(columns) and tgt_idx < len(columns):
                    src_t_idx, src_col = columns[src_idx]
                    tgt_t_idx, tgt_col = columns[tgt_idx]
                    if src_t_idx != -1 and tgt_t_idx != -1:
                        db_schema[tables[src_t_idx].lower()]["foreign_keys"].append({
                            "column": src_col.lower(),
                            "target_table": tables[tgt_t_idx].lower(),
                            "target_column": tgt_col.lower()
                        })
                        
            self.schemas[f"bird_{db_id.lower()}"] = db_schema

    def _load_wikisql_schemas(self):
        # WikiSQL schemas are stored in tabular metadata files
        # We can extract them on the fly as we process WikiSQL splits,
        # but let's prep a register dictionary method
        pass

    def get_schema(self, db_id: str) -> Dict[str, Any]:
        return self.schemas.get(db_id.lower(), {})

    def get_all_db_ids(self) -> List[str]:
        return list(self.schemas.keys())

    def register_schema(self, db_id: str, schema_dict: Dict[str, Any]):
        self.schemas[db_id.lower()] = schema_dict
