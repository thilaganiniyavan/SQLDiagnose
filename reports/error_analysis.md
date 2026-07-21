# Error Analysis Report: CodeBERT SQL Diagnostics

## 1. Introduction
This report provides a detailed error analysis of the baseline CodeBERT diagnostics model evaluated on `dataset_test.csv` (3,901 samples). The goal was to identify the most significant sources of misclassification and guide targeted data augmentation and model optimization.

## 2. Misclassification Metrics
The baseline model achieved an accuracy of **94.80%** on the test set, corresponding to **203 misclassified queries** out of 3,901 total queries.

### Error Breakdowns by Attribute
- **SQL Dialect**: Errors were concentrated in SQLite and PostgreSQL, which have differing rules on reserved keywords and quotation marks.
- **Query Complexity**: Misclassifications were significantly higher for queries with nesting depths $\ge 2$ and queries containing multiple `JOIN` conditions.
- **SQL Error Type**: The majority of errors occurred in `SYNTAX_ERROR` (Class 1) and `SEMANTIC_ERROR` (Class 7).

---

## 3. Five Largest Sources of Error

### 1. RESERVED_KEYWORD_MISUSE (Class 1 - Syntax Error)
- **Model Failure Mode**: The model fails to classify queries that use SQL reserved keywords (e.g. `date`, `year`, `user`, `group`) as identifiers (table or column names) without appropriate quotes (brackets or backticks) as syntax errors.
- **Occurrence Frequency**: 28.5% of Class 1 misclassifications.
- **Underlying Reason**: The pretrained CodeBERT model has a strong semantic prior for English words and often overlooks the strict syntax rules of SQL compilers.
- **Mitigation**: Generated mutated queries where reserved keywords are injected into valid queries without quotes, forcing the model to learn this syntactic boundary.

### 2. MISSING_FROM (Class 1 - Syntax Error)
- **Model Failure Mode**: Omission of the `FROM` keyword after the projection list in SELECT statements.
- **Occurrence Frequency**: 22.1% of Class 1 misclassifications.
- **Underlying Reason**: When queries are long, CodeBERT sometimes fails to align the select columns to their corresponding sources if the sequence of tokens is complex.
- **Mitigation**: Synthesized hard negatives by stripping the `FROM` keyword from valid SELECT queries.

### 3. PARENTHESES_MISMATCH (Class 1 - Syntax Error)
- **Model Failure Mode**: Unmatched brackets/parentheses inside nested subqueries or function calls.
- **Occurrence Frequency**: 16.8% of Class 1 misclassifications.
- **Underlying Reason**: Standard transformers struggle with counting and checking matching pairs over long sequences due to positional encoding limitations.
- **Mitigation**: Generated hard negatives with missing or extra parentheses.

### 4. MISSING_COMMA (Class 1 - Syntax Error)
- **Model Failure Mode**: Missing commas between column names in the SELECT list.
- **Occurrence Frequency**: 14.2% of Class 1 misclassifications.
- **Underlying Reason**: CodeBERT often treats a missing comma as an implicit alias (e.g. `SELECT col1 col2` as `SELECT col1 AS col2`), which is valid in some contexts but invalid when both are actual columns.
- **Mitigation**: Synthesized hard negatives specifically targeting column listing syntax.

### 5. WRONG_JOIN / MISSING_JOIN_CONDITION (Class 7 - Semantic Error)
- **Model Failure Mode**: Omission or misuse of the `ON` clause in joins, or using incorrect columns in the join key.
- **Occurrence Frequency**: 35.6% of Class 7 misclassifications.
- **Underlying Reason**: The model struggles to resolve foreign keys and column schemas across multiple tables without deep schema representation.
- **Mitigation**: Augmented the training set with mutations of join conditions and wrong table references.
