# mutator.py
# Automatically generates SQL errors by applying lexical, semantic, and schema mutations.

import re
import random
from typing import Dict, Any, Tuple, List, Optional

RE_WORDS_AND_PUNCT = re.compile(r"\w+|[^\w\s]")

RESERVED_KEYWORDS = ["SELECT", "FROM", "WHERE", "JOIN", "ON", "GROUP", "BY", "HAVING", "ORDER", "LIMIT", "UNION", "AND", "OR"]

class SQLMutator:
    def __init__(self, seed: int = 42):
        random.seed(seed)

    def _tokenize(self, query: str) -> List[str]:
        return RE_WORDS_AND_PUNCT.findall(query)

    def _detokenize(self, tokens: List[str]) -> str:
        # Standard spacing rules for rebuilding query strings
        query = ""
        for i, token in enumerate(tokens):
            if i == 0:
                query += token
            elif token in [",", ".", "(", ")", ";", "=", "<", ">", "!"]:
                if token == "(" and tokens[i-1].upper() in ["SUM", "AVG", "COUNT", "MAX", "MIN", "LOWER", "UPPER", "ROUND"]:
                    query += token
                elif tokens[i-1] in ["."]:
                    query += token
                else:
                    query += " " + token if tokens[i-1] not in [".", "("] else token
            else:
                if tokens[i-1] in [".", "("]:
                    query += token
                else:
                    query += " " + token
        return query

    def mutate_missing_comma(self, query: str, schema: Dict) -> Optional[Tuple[str, str]]:
        tokens = self._tokenize(query)
        comma_indices = [idx for idx, token in enumerate(tokens) if token == ","]
        if not comma_indices:
            return None
        target = random.choice(comma_indices)
        modified_tokens = tokens[:target] + tokens[target+1:]
        return self._detokenize(modified_tokens), "Removed a comma separator"

    def mutate_missing_from(self, query: str, schema: Dict) -> Optional[Tuple[str, str]]:
        tokens = self._tokenize(query)
        from_indices = [idx for idx, token in enumerate(tokens) if token.upper() == "FROM"]
        if not from_indices:
            return None
        target = random.choice(from_indices)
        modified_tokens = tokens[:target] + tokens[target+1:]
        return self._detokenize(modified_tokens), "Removed the FROM keyword"

    def mutate_wrong_join(self, query: str, schema: Dict) -> Optional[Tuple[str, str]]:
        tokens = self._tokenize(query)
        join_indices = [idx for idx, token in enumerate(tokens) if token.upper() == "JOIN"]
        if not join_indices:
            return None
        target = random.choice(join_indices)
        # Check if there is a prefix modifier (INNER, LEFT, CROSS)
        start_idx = target
        if target > 0 and tokens[target-1].upper() in ["INNER", "LEFT", "CROSS", "RIGHT"]:
            start_idx = target - 1
            
        join_types = ["LEFT JOIN", "RIGHT JOIN", "CROSS JOIN", "INNER JOIN"]
        chosen_join = random.choice(join_types)
        modified_tokens = tokens[:start_idx] + [chosen_join] + tokens[target+1:]
        return self._detokenize(modified_tokens), f"Replaced JOIN syntax with {chosen_join}"

    def mutate_missing_join_condition(self, query: str, schema: Dict) -> Optional[Tuple[str, str]]:
        tokens = self._tokenize(query)
        on_indices = [idx for idx, token in enumerate(tokens) if token.upper() == "ON"]
        if not on_indices:
            return None
        target = random.choice(on_indices)
        # Delete ON and the following comparison tokens until we hit a keyword or end
        end_idx = target + 1
        while end_idx < len(tokens):
            if tokens[end_idx].upper() in ["WHERE", "GROUP", "ORDER", "LIMIT", "JOIN", "LEFT", "RIGHT", "INNER", "UNION", ";"]:
                break
            end_idx += 1
        modified_tokens = tokens[:target] + tokens[end_idx:]
        return self._detokenize(modified_tokens), "Removed the JOIN ON condition clause"

    def mutate_wrong_groupby(self, query: str, schema: Dict) -> Optional[Tuple[str, str]]:
        tokens = self._tokenize(query)
        group_indices = [idx for idx, token in enumerate(tokens) if token.upper() == "GROUP"]
        if not group_indices or (group_indices[0] + 1 >= len(tokens)) or tokens[group_indices[0]+1].upper() != "BY":
            return None
        target = group_indices[0]
        # Find where GROUP BY ends
        end_idx = target + 2
        columns_in_group = []
        col_indices = []
        while end_idx < len(tokens):
            if tokens[end_idx].upper() in ["HAVING", "ORDER", "LIMIT", ";"]:
                break
            if tokens[end_idx] not in [","]:
                columns_in_group.append(tokens[end_idx])
                col_indices.append(end_idx)
            end_idx += 1
            
        if not columns_in_group:
            return None
            
        # Two modes of mutation: remove a grouped column, or add a wrong column
        if random.random() > 0.5 and len(col_indices) > 0:
            remove_idx = random.choice(col_indices)
            # Handle comma removal
            if remove_idx > target + 2 and tokens[remove_idx-1] == ",":
                modified_tokens = tokens[:remove_idx-1] + tokens[remove_idx+1:]
            elif remove_idx + 1 < len(tokens) and tokens[remove_idx+1] == ",":
                modified_tokens = tokens[:remove_idx] + tokens[remove_idx+2:]
            else:
                modified_tokens = tokens[:remove_idx] + tokens[remove_idx+1:]
            description = "Removed a grouping column from the GROUP BY clause"
        else:
            # Add an invalid grouping column
            wrong_col = "unrelated_column_name"
            modified_tokens = tokens[:end_idx] + [",", wrong_col] + tokens[end_idx:]
            description = "Added an invalid column to the GROUP BY clause"
            
        return self._detokenize(modified_tokens), description

    def mutate_aggregate_misuse(self, query: str, schema: Dict) -> Optional[Tuple[str, str]]:
        # Nested aggregates (e.g. SUM(AVG(col)))
        aggregates = ["SUM", "AVG", "COUNT", "MAX", "MIN"]
        tokens = self._tokenize(query)
        agg_indices = [idx for idx, token in enumerate(tokens) if token.upper() in aggregates]
        if not agg_indices:
            # Let's add an invalid aggregate inside the WHERE clause
            where_indices = [idx for idx, token in enumerate(tokens) if token.upper() == "WHERE"]
            if where_indices:
                target = where_indices[0]
                modified_tokens = tokens[:target+1] + ["SUM", "(", "id", ")", ">", "10", "AND"] + tokens[target+1:]
                return self._detokenize(modified_tokens), "Placed an aggregate function inside the WHERE clause"
            return None
            
        target = random.choice(agg_indices)
        nested_agg = random.choice(aggregates)
        modified_tokens = tokens[:target+1] + [nested_agg, "("] + tokens[target+2:]
        # Find closing parenthesis to add the nested close parenthesis
        open_count = 1
        close_idx = target + 3
        while close_idx < len(modified_tokens):
            if modified_tokens[close_idx] == "(":
                open_count += 1
            elif modified_tokens[close_idx] == ")":
                open_count -= 1
                if open_count == 0:
                    modified_tokens = modified_tokens[:close_idx+1] + [")"] + modified_tokens[close_idx+1:]
                    break
            close_idx += 1
            
        return self._detokenize(modified_tokens), f"Nested aggregate functions ({nested_agg} inside {tokens[target]})"

    def mutate_unknown_table(self, query: str, schema: Dict) -> Optional[Tuple[str, str]]:
        if not schema:
            return None
        tokens = self._tokenize(query)
        schema_tables = [t.lower() for t in schema.keys()]
        query_tables = [idx for idx, token in enumerate(tokens) if token.lower() in schema_tables]
        if not query_tables:
            return None
        target = random.choice(query_tables)
        wrong_table_name = tokens[target] + "_tbl_invalid"
        modified_tokens = tokens[:target] + [wrong_table_name] + tokens[target+1:]
        return self._detokenize(modified_tokens), f"Mispelled or referenced unknown table name '{wrong_table_name}'"

    def mutate_unknown_column(self, query: str, schema: Dict) -> Optional[Tuple[str, str]]:
        if not schema:
            return None
        tokens = self._tokenize(query)
        # Retrieve all column names from all tables in the schema
        all_schema_columns = []
        for t_name, t_meta in schema.items():
            all_schema_columns.extend([col.lower() for col in t_meta.get("columns", {}).keys()])
            
        query_col_indices = [idx for idx, token in enumerate(tokens) if token.lower() in all_schema_columns]
        if not query_col_indices:
            return None
        target = random.choice(query_col_indices)
        wrong_col_name = tokens[target] + "_col_invalid"
        modified_tokens = tokens[:target] + [wrong_col_name] + tokens[target+1:]
        return self._detokenize(modified_tokens), f"Mispelled or referenced unknown column name '{wrong_col_name}'"

    def mutate_wrong_alias(self, query: str, schema: Dict) -> Optional[Tuple[str, str]]:
        # Mismatch table aliases
        tokens = self._tokenize(query)
        alias_indices = [idx for idx, token in enumerate(tokens) if token == "." and idx > 0 and idx + 1 < len(tokens)]
        if not alias_indices:
            return None
        target = random.choice(alias_indices)
        # The token before "." is the alias
        old_alias = tokens[target-1]
        wrong_alias = old_alias + "_wrong"
        modified_tokens = tokens[:target-1] + [wrong_alias] + tokens[target:]
        return self._detokenize(modified_tokens), f"Referenced wrong or undefined table alias '{wrong_alias}'"

    def mutate_having_misuse(self, query: str, schema: Dict) -> Optional[Tuple[str, str]]:
        tokens = self._tokenize(query)
        having_indices = [idx for idx, token in enumerate(tokens) if token.upper() == "HAVING"]
        # If HAVING is present, remove GROUP BY
        if having_indices:
            group_indices = [idx for idx, token in enumerate(tokens) if token.upper() == "GROUP"]
            if group_indices:
                target = group_indices[0]
                end_idx = target + 2
                while end_idx < len(tokens):
                    if tokens[end_idx].upper() in ["HAVING", "ORDER", "LIMIT", ";"]:
                        break
                    end_idx += 1
                modified_tokens = tokens[:target] + tokens[end_idx:]
                return self._detokenize(modified_tokens), "Removed the GROUP BY clause while keeping the HAVING clause"
        else:
            # If HAVING is not present, append a malformed HAVING clause
            modified_tokens = tokens + ["HAVING", "COUNT", "(", "*", ")", ">", "5"]
            return self._detokenize(modified_tokens), "Inserted HAVING clause without a GROUP BY statement"
        return None

    def mutate_orderby_misuse(self, query: str, schema: Dict) -> Optional[Tuple[str, str]]:
        tokens = self._tokenize(query)
        order_indices = [idx for idx, token in enumerate(tokens) if token.upper() == "ORDER"]
        if not order_indices or (order_indices[0] + 1 >= len(tokens)) or tokens[order_indices[0]+1].upper() != "BY":
            # Append a malformed ORDER BY
            modified_tokens = tokens + ["ORDER", "BY", "invalid_order_column_name"]
            return self._detokenize(modified_tokens), "Appended an invalid column to the ORDER BY clause"
        target = order_indices[0]
        # Replace the ordered column
        modified_tokens = tokens[:target+2] + ["invalid_order_column_name"]
        return self._detokenize(modified_tokens), "Modified ORDER BY target column to an invalid identifier"

    def mutate_limit_misuse(self, query: str, schema: Dict) -> Optional[Tuple[str, str]]:
        tokens = self._tokenize(query)
        limit_indices = [idx for idx, token in enumerate(tokens) if token.upper() == "LIMIT"]
        if limit_indices:
            target = limit_indices[0]
            if target + 1 < len(tokens):
                # Replace with negative or decimal limit
                bad_limit = random.choice(["-5", "2.5", "'ten'"])
                modified_tokens = tokens[:target+1] + [bad_limit] + tokens[target+2:]
                return self._detokenize(modified_tokens), f"Assigned an invalid value '{bad_limit}' to the LIMIT clause"
        else:
            modified_tokens = tokens + ["LIMIT", "-10"]
            return self._detokenize(modified_tokens), "Appended an invalid negative value to the LIMIT clause"
        return None

    def mutate_nested_query_mistake(self, query: str, schema: Dict) -> Optional[Tuple[str, str]]:
        # Find subquery parenthesis like (SELECT ...) and delete the parenthesis
        tokens = self._tokenize(query)
        for idx in range(len(tokens) - 1):
            if tokens[idx] == "(" and tokens[idx+1].upper() == "SELECT":
                # Find matching closing parenthesis
                open_count = 1
                close_idx = idx + 1
                while close_idx < len(tokens):
                    if tokens[close_idx] == "(":
                        open_count += 1
                    elif tokens[close_idx] == ")":
                        open_count -= 1
                        if open_count == 0:
                            # Delete both index and close_idx parenthesis
                            modified_tokens = tokens[:idx] + tokens[idx+1:close_idx] + tokens[close_idx+1:]
                            return self._detokenize(modified_tokens), "Deleted structural subquery parentheses"
                    close_idx += 1
        return None

    def mutate_parentheses_mismatch(self, query: str, schema: Dict) -> Optional[Tuple[str, str]]:
        tokens = self._tokenize(query)
        paren_indices = [idx for idx, token in enumerate(tokens) if token in ["(", ")"]]
        if not paren_indices:
            # Insert a random parenthesis to create mismatch
            target = random.randint(0, len(tokens))
            modified_tokens = tokens[:target] + ["("] + tokens[target:]
            return self._detokenize(modified_tokens), "Added an unmatched parenthesis"
        target = random.choice(paren_indices)
        modified_tokens = tokens[:target] + tokens[target+1:]
        return self._detokenize(modified_tokens), "Removed a bracket to create a parentheses mismatch"

    def mutate_reserved_keyword_misuse(self, query: str, schema: Dict) -> Optional[Tuple[str, str]]:
        tokens = self._tokenize(query)
        # Select target column in select projections
        all_schema_columns = []
        if schema:
            for t_meta in schema.values():
                all_schema_columns.extend([col.lower() for col in t_meta.get("columns", {}).keys()])
        query_col_indices = [idx for idx, token in enumerate(tokens) if token.lower() in all_schema_columns]
        if not query_col_indices:
            return None
        target = random.choice(query_col_indices)
        keyword = random.choice(["SELECT", "FROM", "WHERE", "GROUP"])
        modified_tokens = tokens[:target] + [keyword] + tokens[target+1:]
        return self._detokenize(modified_tokens), f"Replaced column identifier with reserved SQL keyword '{keyword}'"

    def mutate_function_misuse(self, query: str, schema: Dict) -> Optional[Tuple[str, str]]:
        tokens = self._tokenize(query)
        standard_functions = ["COUNT", "SUM", "AVG", "MIN", "MAX", "LOWER", "UPPER", "ROUND"]
        func_indices = [idx for idx, token in enumerate(tokens) if token.upper() in standard_functions]
        if func_indices:
            target = random.choice(func_indices)
            wrong_func = tokens[target] + "_INVALID_FUNC"
            modified_tokens = tokens[:target] + [wrong_func] + tokens[target+1:]
            return self._detokenize(modified_tokens), f"Replaced valid function call with invalid function name '{wrong_func}'"
        else:
            # Let's wrap a column projection in a non-existent function
            if len(tokens) > 1:
                modified_tokens = [tokens[0], "INVALID_SQL_FUNC", "("] + tokens[1:]
                # Append matching close parenthesis at the next column identifier
                modified_tokens.insert(5, ")")
                return self._detokenize(modified_tokens), "Wrapped column projection in non-existent function 'INVALID_SQL_FUNC'"
        return None

    def mutate_datatype_mismatch(self, query: str, schema: Dict) -> Optional[Tuple[str, str]]:
        tokens = self._tokenize(query)
        # Look for numeric comparisons (e.g. col = 10 or id = 5.0) and replace with string literal
        for idx in range(len(tokens) - 2):
            if tokens[idx+1] in ["=", ">", "<", "!="] and re.match(r"^\d+(\.\d+)?$", tokens[idx+2]):
                modified_tokens = tokens[:idx+2] + ["'abc_datatype_mismatch'"] + tokens[idx+3:]
                return self._detokenize(modified_tokens), "Compared a numeric expression directly to a string literal"
        
        # Fallback: find a column in the schema and append an incompatible type comparison
        if schema:
            for t_name, t_meta in schema.items():
                if t_name in query.lower():
                    cols = t_meta.get("columns", {})
                    for c_name, c_type in cols.items():
                        if c_type in ["INTEGER", "REAL", "NUMERIC"]:
                            suffix = ["AND", f"{t_name}.{c_name}", "=", "'text_value'"] if "WHERE" in [t.upper() for t in tokens] else ["WHERE", f"{t_name}.{c_name}", "=", "'text_value'"]
                            return self._detokenize(tokens + suffix), f"Compared numeric column '{c_name}' to string literal"
                        elif "CHAR" in c_type or "TEXT" in c_type:
                            suffix = ["AND", f"{t_name}.{c_name}", "=", "9999"] if "WHERE" in [t.upper() for t in tokens] else ["WHERE", f"{t_name}.{c_name}", "=", "9999"]
                            return self._detokenize(tokens + suffix), f"Compared string column '{c_name}' to numeric integer"
        return None

    def mutate_null_comparison_errors(self, query: str, schema: Dict) -> Optional[Tuple[str, str]]:
        tokens = self._tokenize(query)
        # Replace IS NULL with = NULL, or IS NOT NULL with != NULL
        for idx in range(len(tokens) - 1):
            if tokens[idx].upper() == "IS" and tokens[idx+1].upper() == "NULL":
                modified_tokens = tokens[:idx] + ["=", "NULL"] + tokens[idx+2:]
                return self._detokenize(modified_tokens), "Replaced 'IS NULL' syntax with '= NULL'"
            if idx + 2 < len(tokens) and tokens[idx].upper() == "IS" and tokens[idx+1].upper() == "NOT" and tokens[idx+2].upper() == "NULL":
                modified_tokens = tokens[:idx] + ["!=", "NULL"] + tokens[idx+3:]
                return self._detokenize(modified_tokens), "Replaced 'IS NOT NULL' syntax with '!= NULL'"
        # If no IS NULL exists, add `= NULL` condition to the end
        modified_tokens = tokens + ["WHERE", "id", "=", "NULL"] if "WHERE" not in [t.upper() for t in tokens] else tokens + ["AND", "id", "=", "NULL"]
        return self._detokenize(modified_tokens), "Appended an invalid null comparison comparison (= NULL)"

    def mutate_duplicate_alias(self, query: str, schema: Dict) -> Optional[Tuple[str, str]]:
        tokens = self._tokenize(query)
        as_indices = [idx for idx, token in enumerate(tokens) if token.upper() == "AS"]
        if len(as_indices) >= 2:
            # Make the second alias identical to the first
            target_1 = as_indices[0]
            target_2 = as_indices[1]
            if target_1 + 1 < len(tokens) and target_2 + 1 < len(tokens):
                alias_1 = tokens[target_1+1]
                modified_tokens = tokens[:target_2+1] + [alias_1] + tokens[target_2+2:]
                return self._detokenize(modified_tokens), f"Assigned duplicate alias '{alias_1}' to multiple SELECT outputs"
        
        # Fallback: append AS duplicate_alias to two projections in select list
        select_idx = -1
        from_idx = len(tokens)
        for idx, token in enumerate(tokens):
            if token.upper() == "SELECT":
                select_idx = idx
            elif token.upper() == "FROM":
                from_idx = idx
                break
                
        if select_idx != -1 and from_idx > select_idx + 1:
            commas = [idx for idx in range(select_idx + 1, from_idx) if tokens[idx] == ","]
            if commas:
                comma_idx = commas[0]
                modified_tokens = tokens[:comma_idx] + ["AS", "dup_col_name"] + tokens[comma_idx:from_idx] + ["AS", "dup_col_name"] + tokens[from_idx:]
                return self._detokenize(modified_tokens), "Assigned duplicate alias 'dup_col_name' to multiple SELECT outputs"
        return None

    def mutate_incorrect_where(self, query: str, schema: Dict) -> Optional[Tuple[str, str]]:
        tokens = self._tokenize(query)
        where_indices = [idx for idx, token in enumerate(tokens) if token.upper() == "WHERE"]
        if not where_indices:
            # Append a malformed where statement
            modified_tokens = tokens + ["WHERE", "AND", "age", ">", "18"]
            return self._detokenize(modified_tokens), "Appended malformed WHERE condition starting with logical AND operator"
        target = where_indices[0]
        # Insert a dangling operator right after WHERE
        modified_tokens = tokens[:target+1] + ["AND"] + tokens[target+1:]
        return self._detokenize(modified_tokens), "Inserted dangling logical operator directly following the WHERE keyword"

    def apply_random_mutation(self, query: str, schema: Dict) -> Tuple[str, str, str]:
        # List of all mutation functions
        mutators = [
            (self.mutate_missing_comma, "MISSING_COMMA"),
            (self.mutate_missing_from, "MISSING_FROM"),
            (self.mutate_wrong_join, "WRONG_JOIN"),
            (self.mutate_missing_join_condition, "MISSING_JOIN_CONDITION"),
            (self.mutate_wrong_groupby, "WRONG_GROUPBY"),
            (self.mutate_aggregate_misuse, "AGGREGATE_MISUSE"),
            (self.mutate_unknown_table, "UNKNOWN_TABLE"),
            (self.mutate_unknown_column, "UNKNOWN_COLUMN"),
            (self.mutate_wrong_alias, "WRONG_ALIAS"),
            (self.mutate_having_misuse, "HAVING_MISUSE"),
            (self.mutate_orderby_misuse, "ORDERBY_MISUSE"),
            (self.mutate_limit_misuse, "LIMIT_MISUSE"),
            (self.mutate_nested_query_mistake, "NESTED_QUERY_MISTAKE"),
            (self.mutate_parentheses_mismatch, "PARENTHESES_MISMATCH"),
            (self.mutate_reserved_keyword_misuse, "RESERVED_KEYWORD_MISUSE"),
            (self.mutate_function_misuse, "FUNCTION_MISUSE"),
            (self.mutate_datatype_mismatch, "DATATYPE_MISMATCH"),
            (self.mutate_null_comparison_errors, "NULL_COMPARISON_ERRORS"),
            (self.mutate_duplicate_alias, "DUPLICATE_ALIAS"),
            (self.mutate_incorrect_where, "INCORRECT_WHERE")
        ]
        
        # Shuffle to select randomly
        random.shuffle(mutators)
        for mutator_fn, error_type in mutators:
            res = mutator_fn(query, schema)
            if res is not None:
                modified_query, description = res
                # Return mutated query, the error label, and the description
                return modified_query, error_type, description
                
        # If no mutations could be applied, fallback to parentheses mismatch (adds a bracket)
        res = self.mutate_parentheses_mismatch(query, schema)
        return res[0], "PARENTHESES_MISMATCH", res[1]
