import os
import sys
import json
import random
from pathlib import Path

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
HFDataset = hf_datasets.Dataset

# Now we can import our package components
from datasets.mutator import SQLMutator
from datasets.validator import SQLValidator
from datasets.schema_resolver import SchemaResolver

import pandas as pd

def get_difficulty(error_type: str) -> str:
    if error_type in ["MISSING_COMMA", "MISSING_FROM", "PARENTHESES_MISMATCH"]:
        return "EASY"
    elif error_type in ["UNKNOWN_TABLE", "UNKNOWN_COLUMN", "WRONG_ALIAS", "NULL_COMPARISON_ERRORS"]:
        return "MEDIUM"
    else:
        return "HARD"

def main():
    project_root = Path(__file__).parent.parent
    processed_dir = project_root / "datasets" / "processed"
    raw_dir = project_root / "datasets" / "raw"
    
    # Initialize helpers
    mutator = SQLMutator(seed=42)
    validator = SQLValidator(raw_dir)
    schema_resolver = SchemaResolver(raw_dir)
    
    # Process train and validation splits
    for split_name, target_count in [("train", 200), ("validation", 50)]:
        csv_path = processed_dir / f"dataset_{split_name}.csv"
        print(f"\nProcessing split: {split_name}")
        df = pd.read_csv(csv_path)
        
        # Parse database_schema and metadata columns from strings back to python structures
        df["database_schema"] = df["database_schema"].apply(json.loads)
        df["metadata"] = df["metadata"].apply(json.loads)
        
        # Get set of valid databases in this split
        split_dbs = set(df["database_name"].unique())
        print(f"Unique databases in {split_name}: {split_dbs}")
        
        # Retrieve all CORRECT queries in this split
        correct_df = df[df["error_type"] == "CORRECT"].copy()
        print(f"Number of correct queries in {split_name} base: {len(correct_df)}")
        
        new_samples = []
        
        # Target classes to generate
        # 1. RESERVED_KEYWORD_MISUSE (SYNTAX_ERROR, Class 1)
        # 2. MISSING_FROM (SYNTAX_ERROR, Class 1)
        # 3. PARENTHESES_MISMATCH (SYNTAX_ERROR, Class 1)
        # 4. MISSING_COMMA (SYNTAX_ERROR, Class 1)
        # 5. CORRECT (Class 0)
        
        correct_queries = correct_df.to_dict("records")
        random.seed(42)
        random.shuffle(correct_queries)
        
        # Generator for RESERVED_KEYWORD_MISUSE
        count = 0
        trials = 0
        while count < target_count and trials < len(correct_queries) * 10:
            item = random.choice(correct_queries)
            query = item["sql_query"]
            db_id = item["database_name"]
            schema = schema_resolver.get_schema(db_id)
            
            res = mutator.mutate_reserved_keyword_misuse(query, schema)
            if res:
                mut_query, desc = res
                is_valid, err = validator.validate_query(mut_query, db_id)
                if not is_valid:
                    new_samples.append({
                        "query_id": f"hard_neg_{split_name}_rkm_{count}",
                        "database_name": db_id,
                        "database_schema": schema,
                        "sql_query": mut_query,
                        "is_valid": False,
                        "error_type": "RESERVED_KEYWORD_MISUSE",
                        "difficulty": "HARD",
                        "source_dataset": "MockDataset_HardNeg",
                        "metadata": {
                            "original_query": query,
                            "modified_query": mut_query,
                            "mutation_description": desc,
                            "sandbox_error": err
                        }
                    })
                    count += 1
            trials += 1
        print(f"Generated {count} RESERVED_KEYWORD_MISUSE hard-negatives.")
        
        # Generator for MISSING_FROM
        count = 0
        trials = 0
        while count < target_count and trials < len(correct_queries) * 10:
            item = random.choice(correct_queries)
            query = item["sql_query"]
            db_id = item["database_name"]
            schema = schema_resolver.get_schema(db_id)
            
            res = mutator.mutate_missing_from(query, schema)
            if res:
                mut_query, desc = res
                is_valid, err = validator.validate_query(mut_query, db_id)
                if not is_valid:
                    new_samples.append({
                        "query_id": f"hard_neg_{split_name}_mf_{count}",
                        "database_name": db_id,
                        "database_schema": schema,
                        "sql_query": mut_query,
                        "is_valid": False,
                        "error_type": "MISSING_FROM",
                        "difficulty": "EASY",
                        "source_dataset": "MockDataset_HardNeg",
                        "metadata": {
                            "original_query": query,
                            "modified_query": mut_query,
                            "mutation_description": desc,
                            "sandbox_error": err
                        }
                    })
                    count += 1
            trials += 1
        print(f"Generated {count} MISSING_FROM hard-negatives.")
        
        # Generator for PARENTHESES_MISMATCH
        count = 0
        trials = 0
        while count < target_count and trials < len(correct_queries) * 10:
            item = random.choice(correct_queries)
            query = item["sql_query"]
            db_id = item["database_name"]
            schema = schema_resolver.get_schema(db_id)
            
            res = mutator.mutate_parentheses_mismatch(query, schema)
            if res:
                mut_query, desc = res
                is_valid, err = validator.validate_query(mut_query, db_id)
                if not is_valid:
                    new_samples.append({
                        "query_id": f"hard_neg_{split_name}_pm_{count}",
                        "database_name": db_id,
                        "database_schema": schema,
                        "sql_query": mut_query,
                        "is_valid": False,
                        "error_type": "PARENTHESES_MISMATCH",
                        "difficulty": "EASY",
                        "source_dataset": "MockDataset_HardNeg",
                        "metadata": {
                            "original_query": query,
                            "modified_query": mut_query,
                            "mutation_description": desc,
                            "sandbox_error": err
                        }
                    })
                    count += 1
            trials += 1
        print(f"Generated {count} PARENTHESES_MISMATCH hard-negatives.")
        
        # Generator for MISSING_COMMA
        count = 0
        trials = 0
        while count < target_count and trials < len(correct_queries) * 10:
            item = random.choice(correct_queries)
            query = item["sql_query"]
            db_id = item["database_name"]
            schema = schema_resolver.get_schema(db_id)
            
            res = mutator.mutate_missing_comma(query, schema)
            if res:
                mut_query, desc = res
                is_valid, err = validator.validate_query(mut_query, db_id)
                if not is_valid:
                    new_samples.append({
                        "query_id": f"hard_neg_{split_name}_mc_{count}",
                        "database_name": db_id,
                        "database_schema": schema,
                        "sql_query": mut_query,
                        "is_valid": False,
                        "error_type": "MISSING_COMMA",
                        "difficulty": "EASY",
                        "source_dataset": "MockDataset_HardNeg",
                        "metadata": {
                            "original_query": query,
                            "modified_query": mut_query,
                            "mutation_description": desc,
                            "sandbox_error": err
                        }
                    })
                    count += 1
            trials += 1
        print(f"Generated {count} MISSING_COMMA hard-negatives.")
        
        # Generator for CORRECT augmentations
        count = 0
        trials = 0
        while count < target_count and trials < len(correct_queries) * 10:
            item = random.choice(correct_queries)
            query = item["sql_query"]
            db_id = item["database_name"]
            schema = schema_resolver.get_schema(db_id)
            
            # Perform a valid query casing / comment / whitespace augmentation
            aug_mode = random.choice(["casing", "comment", "whitespace"])
            aug_query = query
            if aug_mode == "casing":
                tokens = mutator._tokenize(aug_query)
                aug_tokens = [t.lower() if t.upper() in ["SELECT", "FROM", "WHERE", "JOIN", "ON", "GROUP", "BY", "ORDER"] else t for t in tokens]
                aug_query = mutator._detokenize(aug_tokens)
            elif aug_mode == "comment":
                aug_query = f"/* query_var_hn_{count} */ " + aug_query
            else:
                aug_query = aug_query + " "
                
            is_valid, err = validator.validate_query(aug_query, db_id)
            if is_valid:
                new_samples.append({
                    "query_id": f"hard_neg_{split_name}_correct_{count}",
                    "database_name": db_id,
                    "database_schema": schema,
                    "sql_query": aug_query,
                    "is_valid": True,
                    "error_type": "CORRECT",
                    "difficulty": "EASY",
                    "source_dataset": "MockDataset_HardNeg",
                    "metadata": {
                        "original_query": query,
                        "modified_query": aug_query,
                        "mutation_description": "None (Valid Query Augmentation)"
                    }
                })
                count += 1
            trials += 1
        print(f"Generated {count} CORRECT query augmentations.")
        
        # Append new samples
        new_df = pd.DataFrame(new_samples)
        
        # Verify schema isolation: all new samples database names must belong to split_dbs!
        assert set(new_df["database_name"].unique()).issubset(split_dbs), "SCHEMA ISOLATION VIOLATION! Data leakage detected!"
        
        # Re-convert json schema and metadata to string formats for export compatibility
        df["database_schema"] = df["database_schema"].apply(json.dumps)
        df["metadata"] = df["metadata"].apply(json.dumps)
        
        new_df["database_schema"] = new_df["database_schema"].apply(json.dumps)
        new_df["metadata"] = new_df["metadata"].apply(json.dumps)
        
        augmented_df = pd.concat([df, new_df], ignore_index=True)
        print(f"Augmented dataset size for {split_name}: {len(augmented_df)} (Added {len(new_df)} samples)")
        
        # Export all formats
        # 1. CSV
        augmented_df.to_csv(csv_path, index=False)
        # 2. JSON
        json_path = processed_dir / f"dataset_{split_name}.json"
        json_df = augmented_df.copy()
        json_df["database_schema"] = json_df["database_schema"].apply(json.loads)
        json_df["metadata"] = json_df["metadata"].apply(json.loads)
        json_df.to_json(json_path, orient="records", indent=2)
        # 3. Parquet
        parquet_path = processed_dir / f"dataset_{split_name}.parquet"
        augmented_df.to_parquet(parquet_path, index=False)
        
        # 4. HF Dataset
        # Save reference of hf_datasets and replace original datasets module cache
        original_datasets = sys.modules.get("datasets")
        sys.modules["datasets"] = hf_datasets
        try:
            hf_path = processed_dir / f"hf_{split_name}"
            import shutil
            if hf_path.exists():
                shutil.rmtree(hf_path)
            hf_ds = HFDataset.from_pandas(augmented_df)
            hf_ds.save_to_disk(hf_path)
        finally:
            if original_datasets:
                sys.modules["datasets"] = original_datasets
                
        print(f"Successfully exported split {split_name} in all formats.")

if __name__ == "__main__":
    main()
