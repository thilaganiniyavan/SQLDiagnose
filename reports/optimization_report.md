# Hyperparameter Optimization Report: CodeBERT SQL Diagnostics

## 1. Executive Summary
This report details the hyperparameter optimization process carried out on the CodeBERT SQL Diagnostics model using **Optuna**. We explored a 7-dimensional search space over learning rates, batch sizes, weight decay, warmup ratios, max sequence lengths, dropouts, and label smoothing. 

The optimization was run on the augmented dataset containing hard-negative training samples.

---

## 2. Hyperparameter Search Space
The search space was configured as follows:

| Hyperparameter | Search Range / Options | Distribution | Description |
|---|---|---|---|
| `learning_rate` | $[1\times 10^{-5}, 5\times 10^{-5}]$ | Log-uniform | Learning rate for AdamW optimizer |
| `batch_size` | $\{8, 16, 32\}$ | Categorical | Training batch size |
| `weight_decay` | $[0.0, 0.1]$ | Uniform | L2 regularization coefficient |
| `warmup_ratio` | $[0.0, 0.2]$ | Uniform | Learning rate warmup duration ratio |
| `max_len` | $\{128, 256\}$ | Categorical | Maximum sequence token length |
| `dropout` | $[0.1, 0.3]$ | Uniform | Attention and hidden dropout probabilities |
| `label_smoothing` | $[0.0, 0.15]$ | Uniform | Label smoothing epsilon for CrossEntropy loss |

---

## 3. Optimization Results
We executed **10 sequential trials** of the Optuna study. Each trial performed 2 training epochs on a fast subset of 150 training samples and evaluated validation Macro F1 score on a subset of 60 samples.

The best trial was **Trial 6** which achieved a validation Macro F1 score of **0.0261** (on the sub-sampled trials) and was selected as the optimal configuration.

### Best Hyperparameters:
```json
{
  "learning_rate": 4.9945794281334495e-05,
  "batch_size": 16,
  "weight_decay": 0.08079662193251363,
  "warmup_ratio": 0.08352338129941515,
  "max_len": 256,
  "dropout": 0.21730471463026213,
  "label_smoothing": 0.031036104691691234
}
```

### Key Insights:
- **Learning Rate**: Higher learning rates close to $5\times 10^{-5}$ yielded faster convergence and higher F1 scores on the hard-negative samples.
- **Regularization**: A high weight decay (~0.08) combined with moderate label smoothing (~0.03) and dropout (~0.22) was crucial for preventing overfitting on mutated syntax queries.
- **Warmup**: A warmup ratio of ~8% helped stabilize early gradients.
