# Dataset Statistics Report

This report summarizes the metrics, class distribution, and structural parameters of the unified SQL Error Classification dataset.

---

## 1. High-Level Summary
*   **Total Number of Samples**: 12000
*   **Number of Unique Classes**: 22
*   **Average Query Length (Characters)**: 81.67
*   **Maximum Query Length (Characters)**: 214

---

## 2. Class Distribution (Error Categories)
| Class/Error Type | Sample Count | Percentage |
| :--- | :---: | :---: |
| UNKNOWN_COLUMN | 1500 | 12.50% |
| PERMISSION_DENIED | 1500 | 12.50% |
| DUPLICATE_ALIAS | 1500 | 12.50% |
| UNKNOWN_TABLE | 1500 | 12.50% |
| CORRECT | 1500 | 12.50% |
| DATATYPE_MISMATCH | 1500 | 12.50% |
| PARENTHESES_MISMATCH | 372 | 3.10% |
| MISSING_FROM | 369 | 3.08% |
| ORDERBY_MISUSE | 355 | 2.96% |
| INCORRECT_WHERE | 347 | 2.89% |
| RESERVED_KEYWORD_MISUSE | 335 | 2.79% |
| HAVING_MISUSE | 330 | 2.75% |
| FUNCTION_MISUSE | 314 | 2.62% |
| NULL_COMPARISON_ERRORS | 227 | 1.89% |
| AGGREGATE_MISUSE | 99 | 0.83% |
| LIMIT_MISUSE | 93 | 0.78% |
| MISSING_COMMA | 77 | 0.64% |
| WRONG_ALIAS | 36 | 0.30% |
| WRONG_GROUPBY | 15 | 0.12% |
| WRONG_JOIN | 14 | 0.12% |
| MISSING_JOIN_CONDITION | 10 | 0.08% |
| NESTED_QUERY_MISTAKE | 7 | 0.06% |

---

## 3. Difficulty Distribution
| Difficulty Level | Sample Count | Percentage |
| :--- | :---: | :---: |
| HARD | 6419 | 53.49% |
| MEDIUM | 3263 | 27.19% |
| EASY | 2318 | 19.32% |

---

## 4. Source Dataset Distribution
| Source Dataset | Sample Count | Percentage |
| :--- | :---: | :---: |
| MockDataset | 12000 | 100.00% |

---

## 5. Splits Partition Summary
*   **Training Set**: 3937 samples
*   **Validation Set**: 4162 samples
*   **Test Set**: 3901 samples
