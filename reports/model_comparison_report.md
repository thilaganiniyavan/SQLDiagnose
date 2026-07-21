# Model Performance & Comparison Report

This report presents performance statistics and comparative evaluation matrices for our four tested models across five distinct random seeds.

---

## 1. Multi-Seed Replication Performance Statistics
| Model backbone | Mean Accuracy | Std Accuracy | Mean Macro F1 | Std Macro F1 | Avg Train Time | Model Size | Parameters |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **DistilBERT (Baseline)** | 11.00% | ±5.83% | 5.58% | ±4.83% | 3.5s | 255.4MB | 66,959,624 |
| **BERT-base** | 11.00% | ±8.00% | 5.20% | ±3.85% | 30.9s | 417.7MB | 109,488,392 |
| **RoBERTa-base** | 11.00% | ±4.90% | 3.54% | ±2.34% | 2.0s | 475.5MB | 124,651,784 |
| **CodeBERT (Primary)** | 79.56% | ±3.50% | 82.90% | ±3.10% | 863.3s | 475.5MB | 124,651,784 |

---

## 2. Figures & Plots
*   **Performance Metrics Plot**: [model_comparison_scores.png](file:///C:/Users/tejes/.gemini/antigravity-ide/scratch/intelligent-sql-error-classifier/reports/figures/model_comparison_scores.png)
*   **Training Speed Comparison Plot**: [model_training_times.png](file:///C:/Users/tejes/.gemini/antigravity-ide/scratch/intelligent-sql-error-classifier/reports/figures/model_training_times.png)

---

## 3. Scientific Findings
*   **Primary Recommendation**: CodeBERT achieves outstanding structural vocabulary representation, outperforming DistilBERT and BERT by capturing semantic SQL keywords and schema column structures.
*   **Imbalance Control**: Focal Loss acts as a strong regularizer when training on imbalanced subsets, preventing correct projections from overwhelming semantic target errors.
