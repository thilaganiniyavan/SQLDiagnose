# SQL Repair Benchmarks & Evaluations

This report summarizes the performance of the `SQLRepairEngine` in diagnosing and automatically correcting classified SQL syntax, schema, and semantic errors.

## Benchmark 1: UNKNOWN_COLUMN
- **Database**: `company_db`
- **Input Query**: `select id_col_invalid , name from employees`
- **Detected Category**: `UNKNOWN_COLUMN` (Confidence: 98.8%)
- **Explanation**: Referenced column name does not exist on the targeted tables.
- **Suggested Correction**: Mapped unknown column 'id_col_invalid' to 'id'.
- **Corrected SQL Query**: `select id , name from employees`

---

## Benchmark 2: UNKNOWN_TABLE
- **Database**: `company_db`
- **Input Query**: `SELECT emp_id FROM works_on_tbl_invalid ORDER BY emp_id DESC`
- **Detected Category**: `UNKNOWN_TABLE` (Confidence: 98.8%)
- **Explanation**: Referenced table does not exist in the active schema catalog.
- **Suggested Correction**: Mapped unknown table 'works_on_tbl_invalid' to 'works_on'.
- **Corrected SQL Query**: `SELECT emp_id FROM works_on ORDER BY emp_id DESC`

---

## Benchmark 3: DATATYPE_MISMATCH
- **Database**: `company_db`
- **Input Query**: `select emp_id from works_on order by emp_id DESC WHERE works_on.emp_id = 'text_value'`
- **Detected Category**: `DATATYPE_MISMATCH` (Confidence: 98.8%)
- **Explanation**: Datatype mismatch: value type does not match column schema definition.
- **Suggested Correction**: Verify literal types matched to schema columns.
- **Corrected SQL Query**: `select emp_id from works_on order by emp_id DESC WHERE works_on.emp_id = 'text_value'`

---

## Benchmark 4: MISSING_COMMA
- **Database**: `custom_db`
- **Input Query**: `SELECT id name FROM users WHERE age > 18`
- **Detected Category**: `SYNTAX_ERROR` (Confidence: 97.6%)
- **Explanation**: Detected syntactic anomalies (unbalanced syntax, misplaced clauses, or missing delimiters).
- **Suggested Correction**: Inserted missing commas in select projection list.
- **Corrected SQL Query**: `SELECT id, name FROM users WHERE age > 18`

---

## Benchmark 5: INCORRECT_WHERE
- **Database**: `custom_db`
- **Input Query**: `SELECT * WHERE age > 18 FROM users`
- **Detected Category**: `SYNTAX_ERROR` (Confidence: 98.8%)
- **Explanation**: Detected syntactic anomalies (unbalanced syntax, misplaced clauses, or missing delimiters).
- **Suggested Correction**: Moved misplaced WHERE clause to the end of the query.
- **Corrected SQL Query**: `SELECT * FROM users WHERE age > 18`

---

## Benchmark 6: MISSING_JOIN_CONDITION
- **Database**: `university_db`
- **Input Query**: `SELECT name FROM students JOIN enrollments`
- **Detected Category**: `SEMANTIC_ERROR` (Confidence: 99.0%)
- **Explanation**: Semantic error: logical mismatch in joins, aggregations, or projection grouping.
- **Suggested Correction**: Auto-resolved join conditions between 'students' and 'enrollments' using foreign key schema.
- **Corrected SQL Query**: `SELECT name FROM students JOIN enrollments ON enrollments.student_id = students.id`

---

## Benchmark 7: WRONG_GROUPBY
- **Database**: `university_db`
- **Input Query**: `SELECT name, AVG(gpa) FROM students`
- **Detected Category**: `SEMANTIC_ERROR` (Confidence: 98.8%)
- **Explanation**: Semantic error: logical mismatch in joins, aggregations, or projection grouping.
- **Suggested Correction**: Appended missing GROUP BY clause for non-aggregated projections: name.
- **Corrected SQL Query**: `SELECT name, AVG(gpa) FROM students GROUP BY name`

---

## Benchmark 8: DATATYPE_MISMATCH
- **Database**: `custom_db`
- **Input Query**: `SELECT * FROM users WHERE age = '18'`
- **Detected Category**: `DATATYPE_MISMATCH` (Confidence: 98.7%)
- **Explanation**: Datatype mismatch: value type does not match column schema definition.
- **Suggested Correction**: Coerced comparison value for numeric column 'age' by stripping quotes.
- **Corrected SQL Query**: `SELECT * FROM users WHERE age = 18`

---

