# Public SQL Datasets Review

This document reviews publicly available SQL query datasets and recommends the optimal dataset combination for training and validating SQL error detection and classification transformer models.

---

## 1. Public SQL Datasets Profile

### 1. Spider (Yale Lily Lab)
*   **Size:** 10,181 questions, 5,693 unique complex SQL queries across 200 databases (representing 138 domains).
*   **License:** CC BY-SA 4.0
*   **Format:** JSON (queries, token indices, AST representations) and SQLite database files.
*   **Columns:** 
    *   `db_id`: Unique database identifier.
    *   `question`: Natural language description.
    *   `query`: Raw SQL query text.
    *   `sql`: Parsed structured dictionary representing SELECT, WHERE, JOIN, and GROUP BY clauses.
    *   `db_schema` (stored in `tables.json`): Primary keys, foreign keys, column names, column types.
*   **Download Link:** [Yale Lily Lab - Spider](https://yale-lily.github.io/spider)
*   **Suitability:** **Excellent Baseline (Correct Class)**. Provides a large corpus of complex, syntactically and semantically correct SQL queries over multi-table relational databases. Ideal for modeling positive/correct SQL distributions.

---

### 2. WikiSQL (Salesforce)
*   **Size:** 80,654 hand-annotated question-SQL pairs on 24,241 tables from Wikipedia.
*   **License:** BSD 3-Clause
*   **Format:** JSONL files and SQLite tables.
*   **Columns:**
    *   `table_id`: ID of target table.
    *   `question`: Natural language question.
    *   `sql`: Parsed dictionary (`sel` index, `agg` function index, `conds` conditions).
*   **Download Link:** [Salesforce WikiSQL Repository](https://github.com/salesforce/WikiSQL)
*   **Suitability:** **Moderate**. Queries are structurally simple (single-table, no JOINs, limited aggregates). Useful for testing basic tokenization or simple syntactic mappings, but lacks the complexity required for advanced multi-class errors.

---

### 3. BIRD (Big Bench for Large-scale Database Grounding)
*   **Size:** 12,751 Text-to-SQL pairs across 95 large-scale databases (33.4 GB total raw size).
*   **License:** CC BY 4.0
*   **Format:** JSON (questions and metadata) and SQLite databases.
*   **Columns:**
    *   `question_id`: Unique integer.
    *   `db_id`: Target database name.
    *   `question`: Complex analytical question.
    *   `evidence`: Schema descriptions or field lookup advice.
    *   `SQL`: Clean, expert-written SQL query string.
    *   `difficulty`: Difficulty rating.
*   **Download Link:** [BIRD-Bench Official Portal](https://bird-bench.github.io/)
*   **Suitability:** **High**. Focuses on realistic, database-heavy queries with complex views, CTEs, and filters. Excellent for extracting execution-valid queries containing challenging logic.

---

### 4. SParC (Yale Lily Lab)
*   **Size:** 4,298 context-dependent question sequences (totaling 12,726 questions) on 200 databases.
*   **License:** Academic / Research Use
*   **Format:** JSON (compatible with Spider structure).
*   **Columns:**
    *   `database_id`: Database mapping.
    *   `interaction`: List of query turns, each holding `question`, `query`, and `sql` syntax components.
*   **Download Link:** [Yale Lily Lab - SParC](https://yale-lily.github.io/sparc)
*   **Suitability:** **Moderate**. Focuses on multi-turn dialogue context. Only relevant if building sequential/conversational error detectors.

---

### 5. CoSQL (Yale Lily Lab)
*   **Size:** 30,000+ dialogue turns, 10,000+ annotated SQL queries across 200 databases.
*   **License:** Academic / Research Use
*   **Format:** JSON
*   **Columns:** Similar to SParC, with dialogue state metadata and user clarification tags.
*   **Download Link:** [Yale Lily Lab - CoSQL](https://yale-lily.github.io/cosql)
*   **Suitability:** **Low-to-Moderate**. Best suited for conversational repair systems rather than direct static SQL error code diagnostics.

---

### 6. SQLShare (University of Washington)
*   **Size:** 11,137 ad-hoc SQL queries and 3,336 user-uploaded datasets from a multi-year science collaboration platform.
*   **License:** UW eScience License for research.
*   **Format:** SQL text files and CSV tables.
*   **Columns:**
    *   `query`: Raw user-entered SQL text.
    *   `user_id`: Identifier.
    *   `datasets`: Associated views/tables queried.
*   **Download Link:** [UW eScience SQLShare Data Release](https://uwescience.github.io/sqlshare/)
*   **Suitability:** **High (Real-World Human Noise)**. Contains raw, ad-hoc queries written by scientists who were not database experts. Includes real-world syntax errors, slow joins, and structural anomalies.

---

### 7. Kaggle SQL Injection Dataset (e.g., syedsaqlainhussain/sql-injection-dataset)
*   **Size:** ~30,919 rows.
*   **License:** CC0 / Public Domain
*   **Format:** CSV
*   **Columns:**
    *   `Query`: SQL statement string or injection payload.
    *   `Label`: Binary `1` (SQLi attack) or `0` (benign).
*   **Download Link:** [Kaggle SQL Injection Dataset](https://www.kaggle.com/datasets/syedsaqlainhussain/sql-injection-dataset)
*   **Suitability:** **High for Security Errors**. Important if the classifier needs to identify SQL injection security anomalies, but has zero coverage of database engine compilation issues (e.g. missing columns).

---

### 8. NL2SQL-BUGs (KDD 2025)
*   **Size:** 2,018 expert-annotated pairs (1,019 correct, 999 semantically incorrect).
*   **License:** Research Open-Source
*   **Format:** JSON
*   **Columns:**
    *   `question_id`: ID mapping.
    *   `db_id`: Database mapping.
    *   `question`: Target question.
    *   `ground_truth_sql`: Intended SQL logic.
    *   `generated_sql`: Flawed generated query.
    *   `is_error`: Boolean error flag.
    *   `error_type`: Multi-class semantic error category (9 main, 31 subcategories).
    *   `explanation`: Textual reasoning for the mistake.
*   **Download Link:** [NL2SQL-BUGs GitHub](https://github.com/NL2SQL-BUGs/NL2SQL-BUGs.github.io)
*   **Suitability:** **Outstanding (Primary Semantic Source)**. The only public dataset specifically classifying SQL semantic bugs (e.g., incorrect joining keys, aggregate mismatch) into standard error taxonomies.

---

## 2. Recommended Dataset Combinations

### A. Recommended Combination for **SQL Error Detection (Binary Correct/Incorrect)**
*   **Core Datasets:** **Spider** + **BIRD** + **Synthetic Mutators**
*   **Rationale:**
    1.  **Positive Examples:** Standardize the ~18,000 combined SQL statements in Spider and BIRD as the "CORRECT" dataset class.
    2.  **Negative (Syntactic) Examples:** Write a simple query mutation script (located in `datasets/data_processor.py`) to inject syntax bugs into 50% of the Spider/BIRD queries (e.g., dropping commas, introducing unmatched brackets, misspelling keywords like `SELCT` or `JOINN`).
    3.  **Negative (Semantic) Examples:** Incorporate the 999 incorrect queries from **NL2SQL-BUGs** as logically malformed SQL statements that bypass syntactic parsers.

---

### B. Recommended Combination for **SQL Error Classification (Multi-Class)**
*   **Core Datasets:** **NL2SQL-BUGs** + **SQLShare** + **Execution-Engine Mutation Corpus**
*   **Rationale:**
    1.  **Semantic Errors:** Fine-tune the classifier on the **NL2SQL-BUGs** corpus to detect fine-grained semantic errors (e.g., GROUP BY violations, join key mismatches).
    2.  **Real-world Noise:** Train on **SQLShare** queries to classify typical user mistakes.
    3.  **Compilation/Execution Errors:** Generate synthetic semantic errors by running Spider queries through a local python SQLite/PostgreSQL parsing wrapper and programmatically renaming columns or tables in the schema dictionary. This triggers execution-engine exceptions (e.g., table/column missing, datatype mismatch), which are labeled according to their database engine stack traces.
