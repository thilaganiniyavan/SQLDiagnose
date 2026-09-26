# Training Pipeline Architecture

This document describes the architectural design for the deep learning training pipeline. Built on PyTorch and HuggingFace, it incorporates production-grade components to guarantee reproducibility, memory efficiency, and robust evaluation.

---

## 1. Pipeline Execution Flow

```mermaid
flowchart TD
    Init[1. Init Random Seed & Determinism] --> LoadConfig[2. Load Config YAMLs]
    LoadConfig --> LoadData[3. Load Preprocessed Data]
    
    subgraph Cross-Validation Splitter
        LoadData --> KFold[4. Stratified Group K-Fold by Schema ID]
    end

    KFold --> FoldLoop[5. Loop Over Folds 1..K]
    
    subgraph Model Initialization
        FoldLoop --> InitModel[6. Load CodeBERT Classifier]
        FoldLoop --> InitOpt[7. Init AdamW & Warmup Scheduler]
    end
    
    subgraph Training Epoch (Mixed Precision)
        InitModel & InitOpt --> Epoch[8. Epoch Loop]
        Epoch --> Batch[9. Mini-Batch Forward Pass]
        Batch --> AMP[10. FP16 Autocast Activation]
        AMP --> LossCalc[11. Custom Focal Loss Calculation]
        LossCalc --> GradAccum[12. Gradient Accumulation N Steps]
        GradAccum --> Step[13. Optimizer Step & Scaler Update]
    end

    subgraph Logging & Auditing
        Step --> TensorBoard[14. Log Step Metrics to TensorBoard]
        Step --> WandB[15. Log System & Run Stats to W&B]
    end

    subgraph Validation & Checkpoint Guard
        Step --> Eval[16. Evaluation Loop model.eval]
        Eval --> CheckVal{Val Loss Improved?}
        CheckVal -- Yes --> SaveBest[17. Save Checkpoint Model/Opt States]
        CheckVal -- No --> CheckEarly{Patience Exceeded?}
        CheckEarly -- Yes --> EndFold[18. End Fold Early Stopping]
        CheckEarly -- No --> Epoch
    end

    SaveBest --> Epoch
    EndFold --> FoldLoop
```

---

## 2. Component Detail Design

### A. Reproducibility & Random Seed Controller
To ensure training runs are deterministic and experiments are reproducible across CPU and GPU architectures, the pipeline configures:
-   **System Seeds**: Sets seeds for `random`, `numpy`, `torch`, and CUDA.
-   **CuDNN Determinism**: Configures `torch.backends.cudnn.deterministic = True` and disables `torch.backends.cudnn.benchmark` to prevent non-deterministic compiler optimizations.

---

### B. PyTorch Dataset & DataLoader
-   **`SQLClassificationDataset`**: Inherits from `torch.utils.data.Dataset`. It processes tokenized inputs (`input_ids`, `attention_mask`) and target class labels, feeding them as PyTorch tensors.
-   **`DataLoader`**: Configured with pin-memory features to expedite CPU-to-GPU data transfers, utilizing custom samplers if necessary to handle class imbalances.

---

### C. Cross-Validation Splitter
-   **Stratified Group K-Fold**: Splitting is partitioned by **database schema ID** (groups) rather than simple random splits. This ensures that the validation fold contains only queries on unseen databases.
-   **Stratification**: Balances error category label distributions across the $K$-folds.

---

### D. Optimizers & Schedulers
-   **AdamW Optimizer**: Fine-tunes model weights. To avoid over-regularization, weights decay is deactivated for weight matrices associated with biases and LayerNorm parameters.
-   **Linear Learning Rate Scheduler**: Schedules learning rates with a warm-up phase (e.g., initial 10% of total training steps scale linearly from $0$ to `max_lr`), followed by a linear decay to $0$.

---

### E. Efficient Training Features
-   **Mixed Precision (AMP)**: Implements PyTorch’s `torch.cuda.amp.autocast` and `torch.cuda.amp.GradScaler`. Operations are executed in 16-bit float (FP16) where dynamically safe, reducing VRAM usage and model runtime.
-   **Gradient Accumulation**: Aggregates gradients over $N$ steps before executing `optimizer.step()`, facilitating larger virtual batch sizes (e.g. 64) when GPU hardware limits physical batch sizes to smaller values (e.g. 16).

---

### F. Checkpoint Guard & Early Stopping
-   **Checkpoint Manager**: Saves training snapshots containing:
    -   `model_state_dict`: Fine-tuned weights.
    -   `optimizer_state_dict`: Optimizer velocity history.
    -   `scheduler_state_dict`: Scheduler step metrics.
    -   `fold_metadata`: Metrics, labels, and hyperparameters.
-   **Early Stopping**: Monitored on validation loss. If validation performance does not improve for `patience` consecutive checkpoints, training for the current fold is terminated.

---

### G. Evaluation Metrics Loop
-   **Evaluation Mode**: Disables training features (such as dropout layers) via `model.eval()` and suspends gradient computation (`with torch.no_grad()`).
-   **Metrics Computed**:
    -   Average Validation Loss.
    -   Macro/Micro Precision, Recall, and F1-Scores.
    -   Hamming Loss (evaluating classification errors).
    -   Multi-Class Confusion Matrix arrays.

---

### H. Logging and Metrics Tracking
-   **TensorBoard Logger**: Locally logs batch and epoch level metrics (`loss`, `learning_rate`, `grad_norm`) to the `experiments/runs/` folder.
-   **Weights & Biases (W&B)**: Syncs runs to the cloud, recording system resources (CPU, GPU, RAM) and generating interactive plots of the validation metrics.

---

## 3. Abstract Class Structures

The code implementations under `training/train.py` will inherit from standard abstract interfaces:

```python
class ITrainer(ABC):
    @abstractmethod
    def train_fold(self, fold_id: int, train_loader: DataLoader, val_loader: DataLoader) -> Dict[str, Any]:
        """Runs the training loops for a single fold, returning evaluation scores."""
        pass

    @abstractmethod
    def evaluate(self, model: nn.Module, data_loader: DataLoader) -> Dict[str, float]:
        """Evaluates model performance over the specified dataset."""
        pass
```
