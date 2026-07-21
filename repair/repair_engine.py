# repair_engine.py
# Clean Architecture: Use Case Layer
# Implements the SQLRepairEngine for fixing syntax, schema, and semantic errors in SQL.

import re
import json
from typing import Dict, Any, List, Tuple

def levenshtein_distance(s1: str, s2: str) -> int:
    """
    Computes Levenshtein distance between two strings.
    """
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]

def find_best_match(word: str, candidates: List[str]) -> str:
    """
    Finds the closest candidate using substring or Levenshtein distance.
    Returns None if no close match is found.
    """
    if not candidates:
        return None
    # 1. Direct substring matching (case-insensitive)
    for c in candidates:
        if c.lower() in word.lower() or word.lower() in c.lower():
            return c
            
    # 2. Levenshtein fallback
    scores = [(c, levenshtein_distance(word.lower(), c.lower())) for c in candidates]
    best_cand, best_dist = min(scores, key=lambda x: x[1])
    # Match threshold: distance should be small relative to candidate/word length
    if best_dist <= max(2, len(word) // 2):
        return best_cand
    return None

class SQLRepairEngine:
    """
    Hybrid Rule-Based and Fuzzy Matching Engine to repair categorized SQL queries.
    """
    def __init__(self):
        pass

    def repair(
        self,
        query: str,
        predicted_class: int,
        confidence: float,
        schema: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Repairs an input query using the predicted error class and optional schema catalog.
        """
        # Clean query whitespace
        query_clean = re.sub(r'\s+', ' ', query).strip()
        
        # 1. Dispatch to class specific rules
        if predicted_class == 0:  # CORRECT
            return {
                "explanation": "No errors detected. The SQL query appears syntactically and semantically correct.",
                "suggested_correction": "No changes needed.",
                "corrected_query": query,
                "confidence_score": confidence
            }
            
        elif predicted_class == 1:  # SYNTAX ERROR
            return self._repair_syntax(query_clean, confidence)
            
        elif predicted_class in [2, 3]:  # UNKNOWN TABLE OR COLUMN
            return self._repair_schema(query_clean, predicted_class, confidence, schema)
            
        elif predicted_class == 4:  # DATATYPE MISMATCH
            return self._repair_datatype(query_clean, confidence, schema)
            
        elif predicted_class == 5:  # DUPLICATE ALIAS
            return self._repair_alias(query_clean, confidence)
            
        elif predicted_class in [6, 7]:  # SEMANTIC / JOIN / GROUP BY MISUSE
            return self._repair_semantic(query_clean, confidence, schema)
            
        else:
            return {
                "explanation": "Unrecognized error category.",
                "suggested_correction": "Inspect query structure manually.",
                "corrected_query": None,
                "confidence_score": confidence
            }

    def _repair_syntax(self, query: str, confidence: float) -> Dict[str, Any]:
        """
        Applies regex templates to repair syntactic errors.
        """
        corrected = query
        explanation = "Detected syntactic anomalies (unbalanced syntax, misplaced clauses, or missing delimiters)."
        corrections = []
        
        # Rule A: mis-placed WHERE clause (e.g. SELECT * WHERE id=1 FROM users)
        where_before_from = re.search(r"SELECT\s+(.*?)\s+WHERE\s+(.*?)\s+FROM\s+(\w+)(.*)", corrected, re.IGNORECASE)
        if where_before_from:
            projection = where_before_from.group(1)
            where_cond = where_before_from.group(2)
            table_name = where_before_from.group(3)
            remainder = where_before_from.group(4)
            corrected = f"SELECT {projection} FROM {table_name} WHERE {where_cond}{remainder}"
            corrections.append("Moved misplaced WHERE clause to the end of the query.")
            
        # Rule B: Unbalanced parentheses
        open_count = corrected.count('(')
        close_count = corrected.count(')')
        if open_count > close_count:
            corrected += ')' * (open_count - close_count)
            corrections.append(f"Balanced parentheses by adding {open_count - close_count} missing ')'.")
        elif close_count > open_count:
            corrected = '(' * (close_count - open_count) + corrected
            corrections.append(f"Balanced parentheses by prepending {close_count - open_count} missing '('.")
            
        # Rule C: Missing comma in SELECT projection (e.g. SELECT id name FROM users)
        # Find SELECT projection list
        select_match = re.match(r"SELECT\s+(.*?)\s+FROM", corrected, re.IGNORECASE)
        if select_match:
            proj_str = select_match.group(1)
            # Tokenize by spaces and check if there are identifiers without commas
            proj_tokens = [t.strip() for t in proj_str.split() if t.strip()]
            new_tokens = []
            skip = False
            for i in range(len(proj_tokens)):
                if skip:
                    skip = False
                    continue
                # If next token is AS, combine them
                if i + 1 < len(proj_tokens) and proj_tokens[i+1].upper() == 'AS':
                    new_tokens.append(f"{proj_tokens[i]} AS {proj_tokens[i+2] if i+2 < len(proj_tokens) else ''}")
                    skip = True
                    # Skip AS and next alias
                    continue
                new_tokens.append(proj_tokens[i])
            
            # If we reconstructed more commas than items, merge with commas
            reconstructed_proj = ", ".join([t.rstrip(",") for t in new_tokens])
            if reconstructed_proj.count(",") > proj_str.count(","):
                corrected = corrected.replace(proj_str, reconstructed_proj, 1)
                corrections.append("Inserted missing commas in select projection list.")
                
        # Rule D: Reserved keyword misuse as alias/identifier without quotes
        reserved = ["SELECT", "FROM", "WHERE", "JOIN", "ON", "GROUP", "ORDER", "LIMIT"]
        for r_word in reserved:
            # e.g., SELECT select FROM users -> SELECT "select" FROM users
            pattern = rf"\b{r_word}\s+FROM\b"
            if re.search(pattern, corrected, re.IGNORECASE) and r_word.upper() != "SELECT":
                corrected = re.sub(pattern, f'"{r_word}" FROM', corrected, flags=re.IGNORECASE)
                corrections.append(f"Escaped reserved keyword '{r_word}' used as an identifier.")

        return {
            "explanation": explanation,
            "suggested_correction": "; ".join(corrections) if corrections else "Review syntax structures.",
            "corrected_query": corrected if corrections else query,
            "confidence_score": confidence
        }

    def _repair_schema(self, query: str, pred_class: int, confidence: float, schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Fuzzy matches tables/columns against the active database schema catalog.
        """
        if not schema:
            return {
                "explanation": f"Missing catalog context for Class {pred_class} (schema validation violation).",
                "suggested_correction": "Provide the active database schema for auto-repair.",
                "corrected_query": None,
                "confidence_score": confidence
            }
            
        corrected = query
        corrections = []
        schema_tables = list(schema.keys())
        
        if pred_class == 2:  # UNKNOWN TABLE
            explanation = "Referenced table does not exist in the active schema catalog."
            # Extract tables following FROM or JOIN
            table_refs = re.findall(r"\b(?:FROM|JOIN)\s+(\w+)\b", corrected, re.IGNORECASE)
            for t_ref in table_refs:
                if t_ref.lower() not in [st.lower() for st in schema_tables]:
                    # Fuzzy match
                    match = find_best_match(t_ref, schema_tables)
                    if match:
                        # Replace in query (match boundary)
                        corrected = re.sub(rf"\b{t_ref}\b", match, corrected)
                        corrections.append(f"Mapped unknown table '{t_ref}' to '{match}'.")
                        
        else:  # UNKNOWN COLUMN (pred_class == 3)
            explanation = "Referenced column name does not exist on the targeted tables."
            # 1. Find tables referenced in query
            table_refs = re.findall(r"\b(?:FROM|JOIN)\s+(\w+)\b", corrected, re.IGNORECASE)
            valid_tables = [t for t in table_refs if t.lower() in [st.lower() for st in schema_tables]]
            
            # Extract all valid schema columns for these tables
            all_cols = []
            for t in valid_tables:
                # Find matching schema table name
                s_table = [st for st in schema_tables if st.lower() == t.lower()][0]
                all_cols.extend(schema[s_table]["columns"].keys())
                
            # Parse all words in query that could be columns
            words = re.findall(r"\b([a-zA-Z_]\w*)\b", corrected)
            sql_keywords = ["SELECT", "FROM", "WHERE", "JOIN", "ON", "GROUP", "ORDER", "LIMIT", "BY", "AS", "AND", "OR", "IN", "IS", "NOT", "NULL", "COUNT", "SUM", "AVG", "MIN", "MAX"]
            # Exclude tables and keywords
            ignored = [t.lower() for t in table_refs] + [kw.lower() for kw in sql_keywords]
            
            for w in words:
                if w.lower() not in ignored and not w.isdigit():
                    # Check if w is in columns list
                    if w.lower() not in [c.lower() for c in all_cols]:
                        match = find_best_match(w, all_cols)
                        if match:
                            corrected = re.sub(rf"\b{w}\b", match, corrected)
                            corrections.append(f"Mapped unknown column '{w}' to '{match}'.")

        return {
            "explanation": explanation,
            "suggested_correction": "; ".join(corrections) if corrections else "Check table and column name spellings.",
            "corrected_query": corrected if corrections else query,
            "confidence_score": confidence
        }

    def _repair_datatype(self, query: str, confidence: float, schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Coerces datatype mismatches based on catalog types.
        """
        corrected = query
        explanation = "Datatype mismatch: value type does not match column schema definition."
        corrections = []
        
        if not schema:
            return {
                "explanation": explanation,
                "suggested_correction": "Review WHERE comparative values.",
                "corrected_query": query,
                "confidence_score": confidence
            }
            
        # Parse comparison structures like `col = 'literal'` or `col = 123` (allowing fully qualified dots)
        comp_matches = re.finditer(r"\b([\w.]+)\s*(=|>|<|!=)\s*('[^']*'|\d+)", corrected)
        schema_tables = list(schema.keys())
        
        # Gather all columns and their types
        col_types = {}
        for t in schema_tables:
            for c, t_type in schema[t]["columns"].items():
                col_types[c.lower()] = t_type.upper()
                
        for match in comp_matches:
            col_name = match.group(1)
            op = match.group(2)
            val = match.group(3)
            
            # Strip table prefix if fully qualified (e.g. works_on.emp_id -> emp_id)
            lookup_col = col_name.split(".")[-1]
            c_type = col_types.get(lookup_col.lower())
            if c_type:
                is_numeric = c_type in ["INTEGER", "REAL", "FLOAT", "INT"]
                is_quoted = val.startswith("'") and val.endswith("'")
                
                if is_numeric and is_quoted:
                    # Strip quotes
                    unquoted = val.replace("'", "")
                    if unquoted.replace(".", "", 1).isdigit():
                        corrected = corrected.replace(match.group(0), f"{col_name} {op} {unquoted}")
                        corrections.append(f"Coerced comparison value for numeric column '{col_name}' by stripping quotes.")
                elif not is_numeric and not is_quoted:
                    # Add quotes
                    corrected = corrected.replace(match.group(0), f"{col_name} {op} '{val}'")
                    corrections.append(f"Coerced comparison value for string column '{col_name}' by adding single quotes.")

        return {
            "explanation": explanation,
            "suggested_correction": "; ".join(corrections) if corrections else "Verify literal types matched to schema columns.",
            "corrected_query": corrected if corrections else query,
            "confidence_score": confidence
        }

    def _repair_alias(self, query: str, confidence: float) -> Dict[str, Any]:
        """
        Resolves duplicate aliases.
        """
        corrected = query
        explanation = "Alias conflict: duplicate table or column alias specified in query."
        corrections = []
        
        # Regex to find select aliases e.g., AS name
        alias_matches = re.findall(r"\bAS\s+(\w+)\b", corrected, re.IGNORECASE)
        seen = set()
        duplicates = []
        for a in alias_matches:
            if a.lower() in seen:
                duplicates.append(a)
            seen.add(a.lower())
            
        for dup in duplicates:
            # Rename duplicates sequentially
            count = 1
            # We replace occurrence by occurrence
            parts = re.split(rf"\bAS\s+{dup}\b", corrected, flags=re.IGNORECASE)
            rebuilt = parts[0]
            for p in parts[1:]:
                new_alias = f"{dup}_{count}"
                rebuilt += f"AS {new_alias}" + p
                count += 1
            corrected = rebuilt
            corrections.append(f"Renamed duplicate alias '{dup}' to '{dup}_1'.")

        return {
            "explanation": explanation,
            "suggested_correction": "; ".join(corrections) if corrections else "Check query alias uniqueness.",
            "corrected_query": corrected if corrections else query,
            "confidence_score": confidence
        }

    def _repair_semantic(self, query: str, confidence: float, schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Resolves semantic errors (unresolved JOINs, GROUP BY projections, HAVING clause).
        """
        corrected = query
        explanation = "Semantic error: logical mismatch in joins, aggregations, or projection grouping."
        corrections = []
        
        # 1. Join without ON condition (e.g. FROM students JOIN enrollments)
        join_match = re.search(r"FROM\s+(\w+)\s+JOIN\s+(\w+)\b(?!(\s+ON|\s+USING|\s*,))", corrected, re.IGNORECASE)
        if join_match and schema:
            t1 = join_match.group(1)
            t2 = join_match.group(2)
            
            # Check foreign keys in schema to link them
            link_cond = None
            for table_name in [t1, t2]:
                if table_name in schema:
                    fkeys = schema[table_name].get("foreign_keys", [])
                    for fk in fkeys:
                        target = fk["target_table"]
                        if target.lower() in [t1.lower(), t2.lower()]:
                            # Link column
                            src_col = fk["column"]
                            target_col = fk["target_column"]
                            link_cond = f"ON {table_name}.{src_col} = {target}.{target_col}"
                            break
                            
            if link_cond:
                # Insert link condition after JOIN table
                corrected = re.sub(rf"\bJOIN\s+{t2}\b", f"JOIN {t2} {link_cond}", corrected, flags=re.IGNORECASE)
                corrections.append(f"Auto-resolved join conditions between '{t1}' and '{t2}' using foreign key schema.")
                
        # 2. GROUP BY misuse: aggregate projection but missing GROUP BY
        has_agg = any(k in corrected.upper() for k in ["COUNT(", "SUM(", "AVG(", "MIN(", "MAX("])
        has_groupby = "GROUP BY" in corrected.upper()
        
        if has_agg and not has_groupby:
            # We want to group by non-aggregated projections
            select_match = re.match(r"SELECT\s+(.*?)\s+FROM", corrected, re.IGNORECASE)
            if select_match:
                proj_str = select_match.group(1)
                proj_tokens = [t.strip().rstrip(",") for t in proj_str.split(",") if t.strip()]
                
                non_aggs = []
                for tok in proj_tokens:
                    tok_upper = tok.upper()
                    # Check if token is aggregate function
                    if not any(k in tok_upper for k in ["COUNT(", "SUM(", "AVG(", "MIN(", "MAX("]) and tok != "*":
                        # If has alias, extract original column name
                        col_parts = re.split(r"\s+AS\s+", tok, flags=re.IGNORECASE)
                        col_name = col_parts[0].strip()
                        non_aggs.append(col_name)
                        
                if non_aggs:
                    # Append GROUP BY clause
                    groupby_cols = ", ".join(non_aggs)
                    # Insert before ORDER BY or LIMIT if they exist
                    if "ORDER BY" in corrected.upper():
                        corrected = re.sub(r"\bORDER BY\b", f"GROUP BY {groupby_cols} ORDER BY", corrected, flags=re.IGNORECASE)
                    elif "LIMIT" in corrected.upper():
                        corrected = re.sub(r"\bLIMIT\b", f"GROUP BY {groupby_cols} LIMIT", corrected, flags=re.IGNORECASE)
                    else:
                        corrected += f" GROUP BY {groupby_cols}"
                    corrections.append(f"Appended missing GROUP BY clause for non-aggregated projections: {groupby_cols}.")

        # 3. HAVING without GROUP BY
        if "HAVING" in corrected.upper() and not "GROUP BY" in corrected.upper():
            # Find column used in HAVING
            having_match = re.search(r"HAVING\s+(\w+)\b", corrected, re.IGNORECASE)
            if having_match:
                having_col = having_match.group(1)
                # Insert GROUP BY before HAVING
                corrected = re.sub(r"\bHAVING\b", f"GROUP BY {having_col} HAVING", corrected, flags=re.IGNORECASE)
                corrections.append(f"Appended GROUP BY clause for HAVING condition column '{having_col}'.")

        return {
            "explanation": explanation,
            "suggested_correction": "; ".join(corrections) if corrections else "Inspect SQL aggregation and join syntax.",
            "corrected_query": corrected if corrections else query,
            "confidence_score": confidence
        }
