# data_processor.py
# Clean Architecture: Interface Adapter / Frameworks & Drivers
# Handles preprocessing, synthetic mutation, deduplication, class balancing, splits, and exports.

import os
import re
import json
import random
import pandas as pd
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional
import sys
import os

# Save the original local datasets module from sys.modules cache if present
original_local_datasets = sys.modules.get("datasets")
if "datasets" in sys.modules:
    del sys.modules["datasets"]

# Temporarily filter out the current folder's parent from sys.path to avoid name collision
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
original_sys_path = list(sys.path)
sys.path = [p for p in sys.path if os.path.abspath(p) != parent_dir]

import datasets as hf_datasets

# Restore sys.path
sys.path = original_sys_path
# Restore original datasets cache
if original_local_datasets:
    sys.modules["datasets"] = original_local_datasets

# Save a reference to the third-party HuggingFace datasets library
HF_DATASETS_LIB = hf_datasets
HFDataset = hf_datasets.Dataset

from .mutator import SQLMutator
from .validator import SQLValidator
from .schema_resolver import SchemaResolver

class SQLDataProcessor:
    def __init__(self, raw_dir: Path, output_dir: Path, seed: int = 42):
        self.raw_dir = raw_dir
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.seed = seed
        random.seed(seed)
        
        # Instantiate modules
        self.schema_resolver = SchemaResolver(raw_dir)
        self.mutator = SQLMutator(seed)
        self.validator = SQLValidator(raw_dir)
        
        # Private tables list to simulate PERMISSION_DENIED (Class 6)
        self.restricted_tables = ["salary", "password", "secrets", "payment", "credit_card", "security_key", "unauthorized_log"]

    def clean_query(self, query: str) -> str:
        """
        Strips comments, linebreaks, and normalizes whitespaces.
        """
        # Strip single line comments starting with --
        query = re.sub(r"--.*?\n", " ", query)
        # Strip multi-line comments
        query = re.sub(r"/\*.*?\*/", " ", query, flags=re.DOTALL)
        # Normalize whitespace
        query = re.sub(r"\s+", " ", query)
        return query.strip()

    def _load_spider_queries(self) -> List[Dict[str, Any]]:
        queries = []
        spider_path = self.raw_dir / "spider" / "spider"
        train_file = spider_path / "train_spider.json"
        dev_file = spider_path / "dev.json"
        
        for file_path in [train_file, dev_file]:
            if not file_path.exists():
                continue
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data:
                queries.append({
                    "sql_query": self.clean_query(item["query"]),
                    "database_name": item["db_id"].lower(),
                    "source_dataset": "Spider"
                })
        return queries

    def _load_sparc_queries(self) -> List[Dict[str, Any]]:
        queries = []
        sparc_path = self.raw_dir / "sparc" / "sparc"
        train_file = sparc_path / "train.json"
        dev_file = sparc_path / "dev.json"
        
        for file_path in [train_file, dev_file]:
            if not file_path.exists():
                continue
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data:
                db_id = item["database_id"].lower()
                for interaction in item.get("interaction", []):
                    queries.append({
                        "sql_query": self.clean_query(interaction["query"]),
                        "database_name": db_id,
                        "source_dataset": "SParC"
                    })
        return queries

    def _load_cosql_queries(self) -> List[Dict[str, Any]]:
        queries = []
        cosql_path = self.raw_dir / "cosql" / "cosql_dataset"
        train_file = cosql_path / "train.json"
        dev_file = cosql_path / "dev.json"
        
        for file_path in [train_file, dev_file]:
            if not file_path.exists():
                continue
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data:
                db_id = item["database_id"].lower()
                for interaction in item.get("interaction", []):
                    queries.append({
                        "sql_query": self.clean_query(interaction["query"]),
                        "database_name": db_id,
                        "source_dataset": "CoSQL"
                    })
        return queries

    def _load_bird_queries(self) -> List[Dict[str, Any]]:
        queries = []
        bird_file = self.raw_dir / "bird" / "dev.json"
        if not bird_file.exists():
            return []
        with open(bird_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        for item in data:
            queries.append({
                "sql_query": self.clean_query(item["SQL"]),
                "database_name": f"bird_{item['db_id'].lower()}",
                "source_dataset": "BIRD"
            })
        return queries

    def _load_wikisql_queries(self) -> List[Dict[str, Any]]:
        queries = []
        wikisql_data_dir = self.raw_dir / "wikisql" / "WikiSQL-master" / "data"
        if not wikisql_data_dir.exists():
            return []
            
        for file_name in ["train.jsonl", "dev.jsonl", "test.jsonl"]:
            file_path = wikisql_data_dir / file_name
            if not file_path.exists():
                continue
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    item = json.loads(line)
                    # WikiSQL utilizes table_id instead of relational database ID
                    db_id = f"wikisql_{item['table_id'].replace('-', '_').lower()}"
                    queries.append({
                        "sql_query": self.clean_query(item["question"]), # WikiSQL holds target sql representation differently, but we can load standard sql
                        "database_name": db_id,
                        "source_dataset": "WikiSQL"
                    })
        # Return a subset as WikiSQL queries require tables mapping. To keep pipeline robust and SQLite compatible,
        # we will prioritize Spider/BIRD/CoSQL/SParC schemas that run in SQLite connect sandbox, only using WikiSQL if necessary.
        return queries[:1000] if len(queries) > 0 else []

    def get_difficulty(self, error_type: str, query: str) -> str:
        # Rules to score difficulties:
        # Easy: simple syntactic tokens
        # Medium: schema columns references
        # Hard: complex semantic groupings or joints
        if error_type in ["MISSING_COMMA", "MISSING_FROM", "PARENTHESES_MISMATCH"]:
            return "EASY"
        elif error_type in ["UNKNOWN_TABLE", "UNKNOWN_COLUMN", "WRONG_ALIAS", "NULL_COMPARISON_ERRORS"]:
            return "MEDIUM"
        else:
            return "HARD"

    def process_and_build(self, target_samples_per_class: int = 1500) -> Dict[str, pd.DataFrame]:
        print("Loading correct queries from datasets...")
        raw_queries = []
        raw_queries.extend(self._load_spider_queries())
        raw_queries.extend(self._load_sparc_queries())
        raw_queries.extend(self._load_cosql_queries())
        raw_queries.extend(self._load_bird_queries())
        
        if not raw_queries:
            print("No external queries found. Loading fallback mock queries...")
            from .mock_data import get_extended_mock_queries
            mock_items = get_extended_mock_queries()
            for q, db in mock_items:
                raw_queries.append({
                    "sql_query": self.clean_query(q),
                    "database_name": db,
                    "source_dataset": "MockDataset"
                })
        
        # Filter duplicates in correct queries
        seen_queries = set()
        unique_correct = []
        for item in raw_queries:
            key = (item["sql_query"].lower(), item["database_name"].lower())
            if key not in seen_queries:
                seen_queries.add(key)
                unique_correct.append(item)
                
        print(f"Total unique correct queries loaded: {len(unique_correct)}")
        
        # Categorized bins for the 8 target classes
        dataset_bins: Dict[int, List[Dict[str, Any]]] = {i: [] for i in range(8)}
        
        # Fill CORRECT bin (Class 0)
        # Note: We must make sure correct queries execute successfully on the sandbox (where possible)
        print("Verifying and packaging correct queries...")
        correct_count = 0
        for idx, item in enumerate(unique_correct):
            db_id = item["database_name"]
            query = item["sql_query"]
            
            # Execute validation
            is_valid, _ = self.validator.validate_query(query, db_id)
            if is_valid:
                schema = self.schema_resolver.get_schema(db_id)
                sample = {
                    "query_id": f"correct_{correct_count}",
                    "database_name": db_id,
                    "database_schema": schema,
                    "sql_query": query,
                    "is_valid": True,
                    "error_type": "CORRECT",
                    "difficulty": "EASY",
                    "source_dataset": item["source_dataset"],
                    "metadata": {
                        "original_query": query,
                        "modified_query": query,
                        "mutation_description": "None (Valid Query)"
                    }
                }
                dataset_bins[0].append(sample)
                correct_count += 1
                
        print(f"Verified correct queries: {len(dataset_bins[0])}")
        
        # Data augmentation for correct class if we have fewer samples than the target
        if len(dataset_bins[0]) < target_samples_per_class:
            print("Augmenting correct queries...")
            base_correct = list(dataset_bins[0])
            while len(dataset_bins[0]) < target_samples_per_class and base_correct:
                for base in base_correct:
                    if len(dataset_bins[0]) >= target_samples_per_class:
                        break
                    aug_mode = random.choice(["casing", "comment", "whitespace"])
                    aug_query = base["sql_query"]
                    if aug_mode == "casing":
                        tokens = self.mutator._tokenize(aug_query)
                        aug_tokens = [t.lower() if t.upper() in ["SELECT", "FROM", "WHERE", "JOIN", "ON", "GROUP", "BY", "ORDER"] else t for t in tokens]
                        aug_query = self.mutator._detokenize(aug_tokens)
                    elif aug_mode == "comment":
                        aug_query = f"/* query_var_{correct_count} */ " + aug_query
                    else:
                        aug_query = aug_query + " "
                    is_valid, _ = self.validator.validate_query(aug_query, base["database_name"])
                    if is_valid:
                        aug_sample = dict(base)
                        aug_sample["query_id"] = f"correct_{correct_count}"
                        aug_sample["sql_query"] = aug_query
                        dataset_bins[0].append(aug_sample)
                        correct_count += 1
                        
        print(f"Total correct queries after augmentation: {len(dataset_bins[0])}")
        
        # Generate mutations for classes 1-7
        print("Generating synthetic error mutations...")
        mutation_id = 0
        
        # Shuffle queries to distribute mutations evenly
        shuffled_correct = list(dataset_bins[0])
        random.shuffle(shuffled_correct)
        
        # Map mutation types to their target class bins
        class_mapping = {
            "MISSING_COMMA": 1,
            "MISSING_FROM": 1,
            "PARENTHESES_MISMATCH": 1,
            "RESERVED_KEYWORD_MISUSE": 1,
            "INCORRECT_WHERE": 1,
            "UNKNOWN_TABLE": 2,
            "UNKNOWN_COLUMN": 3,
            "DATATYPE_MISMATCH": 4,
            "DUPLICATE_ALIAS": 5,
            "PERMISSION_DENIED": 6,
            "WRONG_JOIN": 7,
            "MISSING_JOIN_CONDITION": 7,
            "WRONG_GROUPBY": 7,
            "AGGREGATE_MISUSE": 7,
            "WRONG_ALIAS": 7,
            "HAVING_MISUSE": 7,
            "ORDERBY_MISUSE": 7,
            "LIMIT_MISUSE": 7,
            "NESTED_QUERY_MISTAKE": 7,
            "FUNCTION_MISUSE": 7,
            "NULL_COMPARISON_ERRORS": 7
        }
        
        # We iterate over our correct queries repeatedly, mutating them and filling bins up to target_samples_per_class
        loop_counter = 0
        while loop_counter < 30:
            loop_counter += 1
            all_filled = all(len(dataset_bins[c]) >= target_samples_per_class for c in range(1, 8))
            if all_filled:
                break
            for item in shuffled_correct:
                db_id = item["database_name"]
                query = item["sql_query"]
                schema = self.schema_resolver.get_schema(db_id)
                trials = 0
                while trials < 5:
                    trials += 1
                    # Check if all error bins are filled to avoid redundant generation
                    all_filled = all(len(dataset_bins[c]) >= target_samples_per_class for c in range(1, 8))
                    if all_filled:
                        break
                    
                    mutated_query, error_type, desc = self.mutator.apply_random_mutation(query, schema)
                    target_class = class_mapping.get(error_type, 7)
                    
                    # Check for PERMISSION_DENIED simulation
                    # If a query contains restricted tables, override its label to PERMISSION_DENIED
                    if any(rest_t in mutated_query.lower() for rest_t in self.restricted_tables):
                        target_class = 6
                        error_type = "PERMISSION_DENIED"
                        desc = "Accessed restricted database table causing permission denial"
                    
                    # If target bin is already filled, continue to find other mutation classes
                    if len(dataset_bins[target_class]) >= target_samples_per_class:
                        continue
                        
                    # Run mutated query against validation sandbox
                    is_valid, sandbox_err = self.validator.validate_query(mutated_query, db_id)
                    # Verify that it indeed fails, except for permission and datatype mismatch errors
                    if not is_valid or target_class in [4, 6]:
                        sample = {
                            "query_id": f"mutated_{mutation_id}",
                            "database_name": db_id,
                            "database_schema": schema,
                            "sql_query": mutated_query,
                            "is_valid": False,
                            "error_type": error_type,
                            "difficulty": self.get_difficulty(error_type, mutated_query),
                            "source_dataset": item["source_dataset"],
                            "metadata": {
                                "original_query": query,
                                "modified_query": mutated_query,
                                "mutation_description": desc,
                                "sandbox_error": sandbox_err
                            }
                        }
                        dataset_bins[target_class].append(sample)
                        mutation_id += 1
                        break # Successful mutation, skip to next query
                    
        # Log final class size profiles
        print("Final class balance count:")
        for c, samples in dataset_bins.items():
            print(f"Class {c} ({self.get_class_name(c)}): {len(samples)} samples")
            
        # Compile everything into a unified dataset
        all_samples = []
        for c in range(8):
            # Trim to ensure perfect class balance where possible
            trimmed = dataset_bins[c][:target_samples_per_class]
            all_samples.extend(trimmed)
            
        random.shuffle(all_samples)
        
        # Split train, validation, and test datasets based on database Group Split
        # This guarantees zero schema leakage between divisions
        all_dbs = list(set([item["database_name"] for item in all_samples]))
        random.shuffle(all_dbs)
        
        # Split databases: Train, Val, Test get distinct databases if we have sufficient count
        num_dbs = len(all_dbs)
        if num_dbs >= 5:
            train_dbs = set(all_dbs[:int(num_dbs * 0.7)])
            val_dbs = set(all_dbs[int(num_dbs * 0.7):int(num_dbs * 0.85)])
            test_dbs = set(all_dbs[int(num_dbs * 0.85):])
        else:
            # Fallback for small DB list (e.g. mock dataset where num_dbs = 3)
            # Assign at least 1 database to each partition to ensure non-zero sizes
            train_dbs = {all_dbs[0]}
            val_dbs = {all_dbs[1]} if num_dbs > 1 else {all_dbs[0]}
            test_dbs = {all_dbs[2]} if num_dbs > 2 else {all_dbs[0]}
        
        train_samples = [s for s in all_samples if s["database_name"] in train_dbs]
        val_samples = [s for s in all_samples if s["database_name"] in val_dbs]
        test_samples = [s for s in all_samples if s["database_name"] in test_dbs]
        
        print(f"Database splits: Train DBs={len(train_dbs)}, Val DBs={len(val_dbs)}, Test DBs={len(test_dbs)}")
        print(f"Sample splits: Train={len(train_samples)}, Val={len(val_samples)}, Test={len(test_samples)}")
        
        splits = {
            "train": pd.DataFrame(train_samples),
            "validation": pd.DataFrame(val_samples),
            "test": pd.DataFrame(test_samples)
        }
        
        self.export_datasets(splits)
        self.generate_statistics_report(splits)
        
        return splits

    def get_class_name(self, class_id: int) -> str:
        names = {
            0: "CORRECT",
            1: "SYNTAX_ERROR",
            2: "TABLE_NOT_FOUND",
            3: "COLUMN_NOT_FOUND",
            4: "DATA_TYPE_MISMATCH",
            5: "AMBIGUOUS_COLUMN",
            6: "PERMISSION_DENIED",
            7: "SEMANTIC_VIOLATION"
        }
        return names.get(class_id, "UNKNOWN")

    def export_datasets(self, splits: Dict[str, pd.DataFrame]):
        print("Exporting datasets...")
        for name, df in splits.items():
            # Export to JSON
            json_path = self.output_dir / f"dataset_{name}.json"
            df.to_json(json_path, orient="records", indent=2)
            
            # Export to CSV
            csv_path = self.output_dir / f"dataset_{name}.csv"
            # Flatten dicts for clean CSV structure
            flat_df = df.copy()
            flat_df["database_schema"] = flat_df["database_schema"].apply(json.dumps)
            flat_df["metadata"] = flat_df["metadata"].apply(json.dumps)
            flat_df.to_csv(csv_path, index=False)
            
            # Export to Parquet
            parquet_path = self.output_dir / f"dataset_{name}.parquet"
            flat_df.to_parquet(parquet_path, index=False)
            
            # Export to HuggingFace Dataset
            # Temporarily swap datasets module to HuggingFace library to avoid serialization circular references
            original_datasets = sys.modules.get("datasets")
            sys.modules["datasets"] = HF_DATASETS_LIB
            try:
                hf_path = self.output_dir / f"hf_{name}"
                hf_ds = HFDataset.from_pandas(flat_df)
                hf_ds.save_to_disk(hf_path)
            finally:
                if original_datasets:
                    sys.modules["datasets"] = original_datasets
            
        print("Dataset exports completed successfully.")

    def generate_statistics_report(self, splits: Dict[str, pd.DataFrame]):
        print("Generating statistics report...")
        report_path = self.output_dir.parent / "reports" / "dataset_statistics_report.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Combine splits to generate global statistics
        full_df = pd.concat([splits["train"], splits["validation"], splits["test"]], ignore_index=True)
        
        num_samples = len(full_df)
        num_classes = full_df["error_type"].nunique()
        class_counts = full_df["error_type"].value_counts()
        avg_query_len = full_df["sql_query"].apply(len).mean()
        max_query_len = full_df["sql_query"].apply(len).max()
        difficulty_dist = full_df["difficulty"].value_counts()
        source_dist = full_df["source_dataset"].value_counts()
        
        # Build Report Markdown Content
        report_content = f"""# Dataset Statistics Report

This report summarizes the metrics, class distribution, and structural parameters of the unified SQL Error Classification dataset.

---

## 1. High-Level Summary
*   **Total Number of Samples**: {num_samples}
*   **Number of Unique Classes**: {num_classes}
*   **Average Query Length (Characters)**: {avg_query_len:.2f}
*   **Maximum Query Length (Characters)**: {max_query_len}

---

## 2. Class Distribution (Error Categories)
| Class/Error Type | Sample Count | Percentage |
| :--- | :---: | :---: |
"""
        for err_type, count in class_counts.items():
            percentage = (count / num_samples) * 100
            report_content += f"| {err_type} | {count} | {percentage:.2f}% |\n"
            
        report_content += f"""
---

## 3. Difficulty Distribution
| Difficulty Level | Sample Count | Percentage |
| :--- | :---: | :---: |
"""
        for diff, count in difficulty_dist.items():
            percentage = (count / num_samples) * 100
            report_content += f"| {diff} | {count} | {percentage:.2f}% |\n"
            
        report_content += f"""
---

## 4. Source Dataset Distribution
| Source Dataset | Sample Count | Percentage |
| :--- | :---: | :---: |
"""
        for src, count in source_dist.items():
            percentage = (count / num_samples) * 100
            report_content += f"| {src} | {count} | {percentage:.2f}% |\n"
            
        report_content += f"""
---

## 5. Splits Partition Summary
*   **Training Set**: {len(splits["train"])} samples
*   **Validation Set**: {len(splits["validation"])} samples
*   **Test Set**: {len(splits["test"])} samples
"""
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_content)
            
        print(f"Report written to {report_path.absolute()}")
