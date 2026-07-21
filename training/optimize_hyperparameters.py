import sys
import os
from pathlib import Path
import json

# Add project root to the beginning of sys.path to prioritize local datasets package
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load local datasets package first to populate sys.modules["datasets"]
import datasets as local_datasets

# Now handle HuggingFace datasets conflict
original_local_datasets = sys.modules.get("datasets")
if "datasets" in sys.modules:
    del sys.modules["datasets"]

# Filter out project_root from sys.path to load third-party HF datasets
original_sys_path = list(sys.path)
sys.path = [p for p in sys.path if os.path.abspath(p) != os.path.abspath(str(project_root))]

import datasets as hf_datasets

# Restore sys.path and sys.modules
sys.path = original_sys_path
if original_local_datasets:
    sys.modules["datasets"] = original_local_datasets

HFDataset = hf_datasets.Dataset

import optuna
import pandas as pd
import numpy as np
import torch
from transformers import AutoTokenizer
from training.train import run_training_pipeline

def objective(trial):
    # Suggest hyperparameters
    learning_rate = trial.suggest_float("learning_rate", 1e-5, 5e-5, log=True)
    batch_size = trial.suggest_categorical("batch_size", [8, 16, 32])
    weight_decay = trial.suggest_float("weight_decay", 0.0, 0.1)
    warmup_ratio = trial.suggest_float("warmup_ratio", 0.0, 0.2)
    max_len = trial.suggest_categorical("max_len", [128, 256])
    dropout = trial.suggest_float("dropout", 0.1, 0.3)
    label_smoothing = trial.suggest_float("label_smoothing", 0.0, 0.15)
    
    print(f"\n--- Optuna Trial {trial.number} ---")
    print(f"Parameters: LR={learning_rate:.2e}, BS={batch_size}, WD={weight_decay:.3f}, WR={warmup_ratio:.2f}, MaxLen={max_len}, Dropout={dropout:.2f}, LabelSmoothing={label_smoothing:.2f}")
    
    try:
        # Load train/validation data
        processed_dir = project_root / "datasets" / "processed"
        train_df = pd.read_csv(processed_dir / "dataset_train.csv")
        val_df = pd.read_csv(processed_dir / "dataset_validation.csv")
        
        # Sub-sample datasets to speed up Optuna trial
        train_subset = train_df.sample(min(150, len(train_df)), random_state=42)
        val_subset = val_df.sample(min(60, len(val_df)), random_state=42)
        
        # Save subsets to temporary files
        train_subset.to_csv(processed_dir / "dataset_train_temp.csv", index=False)
        val_subset.to_csv(processed_dir / "dataset_validation_temp.csv", index=False)
        
        # Swap temporary files into place for the training pipeline
        os.replace(processed_dir / "dataset_train.csv", processed_dir / "dataset_train_orig.csv")
        os.replace(processed_dir / "dataset_validation.csv", processed_dir / "dataset_validation_orig.csv")
        os.replace(processed_dir / "dataset_train_temp.csv", processed_dir / "dataset_train.csv")
        os.replace(processed_dir / "dataset_validation_temp.csv", processed_dir / "dataset_validation.csv")
        
        run_results = None
        try:
            # We run with quick_train=False, save_checkpoints=False, epochs=2 to make it very fast!
            # Pass a dummy subdirectory to checkpoint_dir to prevent loading existing files.
            dummy_checkpoint_dir = project_root / "experiments" / "exp_claudios_codebert-base_42" / "checkpoints" / "temp_optuna"
            
            run_results = run_training_pipeline(
                backbone="claudios/codebert-base",
                seed=42,
                quick_train=False,
                loss_name="cross_entropy",
                learning_rate=learning_rate,
                batch_size=batch_size,
                weight_decay=weight_decay,
                warmup_ratio=warmup_ratio,
                max_len=max_len,
                dropout=dropout,
                label_smoothing=label_smoothing,
                epochs=2,
                save_checkpoints=False,
                checkpoint_dir=dummy_checkpoint_dir
            )
        finally:
            # Restore original train and validation files
            os.replace(processed_dir / "dataset_train_orig.csv", processed_dir / "dataset_train.csv")
            os.replace(processed_dir / "dataset_validation_orig.csv", processed_dir / "dataset_validation.csv")
            
        if run_results and "metrics" in run_results:
            macro_f1 = run_results["metrics"]["report"].get("macro avg", {}).get("f1-score", 0.0)
            print(f"Trial {trial.number} completed. Macro F1: {macro_f1:.4f}")
            return macro_f1
        else:
            return 0.0
    except Exception as e:
        print(f"Trial {trial.number} failed: {e}")
        return 0.0

def main():
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    
    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=10)
            
    print("\n=== Hyperparameter Optimization Completed ===")
    print("Best Trial:")
    trial = study.best_trial
    print(f"  Value (Validation Macro F1): {trial.value:.4f}")
    print("  Parameters: ")
    for k, v in trial.params.items():
        print(f"    {k}: {v}")
        
    # Save the best parameters
    best_params_path = project_root / "experiments" / "best_hyperparameters.json"
    best_params_path.parent.mkdir(parents=True, exist_ok=True)
    with open(best_params_path, "w", encoding="utf-8") as f:
        json.dump(trial.params, f, indent=2)
    print(f"Best hyperparameters saved to {best_params_path}")

if __name__ == "__main__":
    main()
