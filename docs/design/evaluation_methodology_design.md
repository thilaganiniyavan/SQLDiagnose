# Evaluation Methodology & Experiment Design

This document details the evaluation framework and experimental setups designed for the SQL error classification system. To meet publication-grade standards (suitable for ACL/EMNLP/KDD), this methodology defines rigorous performance metrics, computational efficiency audits, statistical significance validations, and standardized experimental baselines.

---

## 1. Multi-Dimensional Metrics Framework

The system is evaluated across three primary dimensions: **Classification Performance**, **Computational Efficiency**, and **Operational Serving Metrics**.

### A. Classification Performance Metrics
SQL error datasets feature high class imbalance (prevalence of correct queries and syntax errors, sparse semantic errors). Thus, macro-averaged metrics are prioritized:

1.  **Overall Accuracy**: Overall proportion of correctly predicted queries.
2.  **Precision, Recall, & F1 (Per-Class)**: Evaluates diagnostic capability for individual categories (e.g., how reliably we isolate `DATA_TYPE_MISMATCH`).
3.  **Macro-Averaged F1 ($F_1^{\text{macro}}$)**: Primary classification metric. Computes F1 independently for each class and averages them, treating all classes equally regardless of frequency:
    $$F_1^{\text{macro}} = \frac{1}{C} \sum_{c=1}^C F_1^c$$
4.  **Weighted-Averaged F1 ($F_1^{\text{weighted}}$)**: Averages per-class F1 weighted by support (number of true instances of that class), representing overall performance.
5.  **Multi-Class Confusion Matrix ($M$)**: Visualizes error distributions. Reveals misclassification clusters (e.g., whether the model confuses `TABLE_NOT_FOUND` with `COLUMN_NOT_FOUND`).
6.  **Receiver Operating Characteristic (ROC) & Area Under Curve (AUC)**: Evaluates classification threshold adjustments for each class, plotted via One-vs-Rest (OvR).
7.  **Precision-Recall (PR) Curves**: Plotted for each class. PR curves provide a more realistic assessment of classification performance on highly imbalanced classes than ROC.

---

### B. Computational Efficiency & Profile Metrics
Audits system resources consumed during lifecycle stages:

1.  **Training Time**: Total execution time, average epoch duration, and step processing speed (samples/sec).
2.  **Inference Speed**: Total validation set evaluation duration, and average batch evaluation time.
3.  **Peak Training Memory**: Measured in Gigabytes using PyTorch's memory tracking:
    ```python
    peak_vram = torch.cuda.max_memory_allocated() / (1024 ** 3)
    ```
4.  **Model Disk Footprint & Parameters**: Total trainable parameters, total non-trainable parameters, and model weight footprint on disk (MB).

---

### C. Operational Serving Metrics
Evaluates model behavior when serving traffic under FastAPI:

1.  **Serving Latency (P50, P90, P99)**: The 50th, 90th, and 99th percentile response latencies (measured in milliseconds) for inference requests over a workload.
2.  **Throughput**: Queries processed per second (QPS) under varying concurrency loads.
3.  **Active Serving Memory**: RAM and VRAM footprint in active serving mode.

---

## 2. Statistical Significance Testing

To verify that model performance improvements are statistically sound rather than artifacts of seed selection, we define three significance tests:

### Test 1: McNemar’s Test (Categorical Predictions Comparison)
*   **Purpose**: Compares two classifiers (e.g., our proposed CodeBERT vs. the DistilBERT baseline) on the same test set.
*   **Methodology**: Operates on a $2 \times 2$ contingency table tracking agreement/disagreement:
    -   $n_{00}$: Both models predicted incorrectly.
    -   $n_{11}$: Both models predicted correctly.
    -   $n_{01}$: Model A incorrect, Model B correct.
    -   $n_{10}$: Model A correct, Model B incorrect.
*   **Formula**:
    $$\chi^2 = \frac{(|n_{01} - n_{10}| - 1)^2}{n_{01} + n_{10}}$$
*   **Threshold**: Reject the null hypothesis (that both models have equivalent error rates) if the p-value $< 0.05$ at 1 degree of freedom.

### Test 2: Wilcoxon Signed-Rank Test (Cross-Validation Metrics)
*   **Purpose**: Evaluates whether average fold metrics (e.g., Macro F1) across the K-fold splits are significantly higher for our proposed model compared to baselines.
*   **Methodology**: A non-parametric paired test comparing the metric difference across identical cross-validation folds.

### Test 3: Welch’s t-test (Serving Latency Analysis)
*   **Purpose**: Compares inference serving latency profiles across repeated runs (concurrency workloads).
*   **Methodology**: Standard t-test that does not assume equal variances, testing the hypothesis that serving speeds differ significantly.

---

## 3. Publication-Quality Experiment Designs

We outline four standardized experiments to benchmark the system:

### Experiment 1: Baseline Comparison Matrix
*   **Objective**: Compare our primary model (CodeBERT) against standard baselines across all metrics.
*   **Target Output Table (LaTeX/Markdown)**:
| Model | Param Count | Val Macro F1 | Val Accuracy | VRAM (Peak) | Latency (P99) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **TinyBERT** | 14.5M | | | | |
| **DistilBERT** | 66M | | | | |
| **BERT** | 110M | | | | |
| **RoBERTa** | 125M | | | | |
| **PLBART** | 140M | | | | |
| **CodeT5** | 220M | | | | |
| **CodeBERT (Ours)** | 125M | | | | |

---

### Experiment 2: Ablation Study
*   **Objective**: Quantify the impact of key preprocessing and training pipeline choices.
*   **Configurations Evaluated**:
    1.  **Baseline**: CodeBERT with standard cross-entropy loss and raw queries.
    2.  **+ Schema Prefix**: Evaluating the impact of prepending table definitions.
    3.  **+ Data Augmentation**: Evaluating the impact of adding mutated queries to minority classes.
    4.  **+ Focal Loss (Full)**: Incorporating Focal Loss to handle class imbalance.

---

### Experiment 3: Out-of-Domain Generalization Test
*   **Objective**: Test model resilience to unseen schemas (distribution shift).
*   **Methodology**: Compare validation performance on **In-Domain Splits** (validation folds containing schemas seen during training) against **Out-of-Domain Splits** (cross-validation folds partitioned by database group ID). Shows whether the model learns general SQL grammar rather than memorizing schema tables.

---

### Experiment 4: Accuracy-Throughput Pareto Curve
*   **Objective**: Visualize the trade-off between model accuracy (Macro F1) and serving speed (Queries Per Second).
*   **Methodology**: Plot Macro F1 score on the Y-axis against QPS on the X-axis for all models, highlighting Pareto-optimal configurations to guide real-world deployments.
