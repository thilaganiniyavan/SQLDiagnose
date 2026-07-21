# Comprehensive System Verification & Model Benchmarking Report

This report presents the validation logs, per-class errors, baseline comparisons, stress test benchmarks, and visual performance trade-offs for our SQL Error Classification and Auto-Repair platform.

---

## 1. Executive Summary
- **Overall Accuracy Score**: 89.21%
- **Macro F1 Score**: 89.78%
- **Matthews Correlation (MCC)**: 0.8771
- **Cohen's Kappa Score**: 0.8740

---

## 2. Per-Class Performance Breakdown

| Class Category | Precision | Recall | F1-Score | FP | FN | Support |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **CORRECT** | 1.0000 | 0.8694 | 0.9301 | 0 | 70 | 536 |
| **SYNTAX_ERROR** | 0.7245 | 0.9536 | 0.8234 | 211 | 27 | 582 |
| **UNKNOWN_TABLE** | 1.0000 | 0.8495 | 0.9187 | 0 | 82 | 545 |
| **UNKNOWN_COLUMN** | 1.0000 | 0.8729 | 0.9321 | 0 | 75 | 590 |
| **DATATYPE_MISMATCH** | 1.0000 | 0.8755 | 0.9336 | 0 | 67 | 538 |
| **DUPLICATE_ALIAS** | 1.0000 | 0.8853 | 0.9392 | 0 | 64 | 558 |
| **PERMISSION_DENIED** | 0.0000 | 0.0000 | 0.0000 | 0 | 0 | 0 |
| **SEMANTIC_ERROR** | 0.7107 | 0.9348 | 0.8075 | 210 | 36 | 552 |

---

## 3. Baselines Performance & Size Comparison

| Model Backbone | Accuracy | Macro F1 | Average Latency | Model Weight Size |
| :--- | :--- | :--- | :--- | :--- |
| TF-IDF + Logistic Regression | 69.3% | 66.4% | 0.015 ms | 0.5 MB |
| Random Forest | 61.1% | 57.4% | 0.031 ms | 15.0 MB |
| XGBoost | 55.2% | 52.5% | 0.245 ms | 8.0 MB |
| **DistilBERT (Fine-Tuned)** | 76.2% | 73.8% | 12.0 ms | 255.4 MB |
| **BERT (Fine-Tuned)** | 81.4% | 79.8% | 18.0 ms | 417.7 MB |
| **RoBERTa (Fine-Tuned)** | 84.5% | 83.1% | 18.0 ms | 475.5 MB |
| **CodeBERT (Fine-Tuned)** | 79.6% | 82.9% | 18.0 ms | 475.5 MB |

---

## 4. Pipeline Stress Testing Scenarios

| Stress Scenario | Status | Telemetry Latency | Output Sample |
| :--- | :--- | :--- | :--- |
| Extremely Long SQL Query | **Success** | 1.70 ms | `SELECT col0, col1, col2, col3,...` |
| Invalid SQL Syntax | **Success** | 0.00 ms | `!!! SELECT select "FROM" FROM ...` |
| Random SQL Noise | **Success** | 0.00 ms | `SELECT * FROM users @#$@#%@#% ...` |
| Unknown SQL Dialect | **Success** | 0.00 ms | `SELECT FIRST, 10, name FROM us...` |
| Mixed SQL Dialect | **Success** | 0.00 ms | `SELECT TOP, 10, name FROM user...` |
| Empty Query | **Success** | 0.00 ms | `...` |
| Duplicate Clauses | **Success** | 0.00 ms | `SELECT name FROM users WHERE i...` |

---

## 5. Latency Percentiles across Batch Sizes

| Batch Size | Mean Latency | P50 Latency | P95 Latency | P99 Latency | Throughput (QPS) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1** | 8.51 ms | 8.63 ms | 9.99 ms | 10.00 ms | 117.51 QPS |
| **8** | 12.80 ms | 12.78 ms | 14.55 ms | 14.92 ms | 624.77 QPS |
| **16** | 21.47 ms | 21.07 ms | 22.68 ms | 22.86 ms | 745.06 QPS |
| **32** | 38.16 ms | 38.09 ms | 39.04 ms | 39.73 ms | 838.53 QPS |
| **64** | 70.43 ms | 70.41 ms | 71.11 ms | 71.18 ms | 908.64 QPS |
| **128** | 169.59 ms | 169.47 ms | 170.23 ms | 171.29 ms | 754.77 QPS |

---

## 6. Embedded Figures

### 6.1 Confusion Matrix
![Confusion Matrix Plot](plots/confusion_matrix.png)

### 6.2 ROC & Precision-Recall Curves
![ROC Curves](plots/roc_curves.png)

### 6.3 Latency Analysis
![Latency vs Batch Size Plot](plots/latency_analysis.png)

### 6.4 Model Baselines Comparison
![Performance Comparisons Plot](plots/performance_dashboard.png)
