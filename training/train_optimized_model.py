import sys
import os
from pathlib import Path
import json
import shutil

# Add project root to path and handle HF datasets conflict
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import datasets as local_datasets
original_local_datasets = sys.modules.get("datasets")
if "datasets" in sys.modules:
    del sys.modules["datasets"]

parent_dir = os.path.abspath(str(project_root))
original_sys_path = list(sys.path)
sys.path = [p for p in sys.path if os.path.abspath(p) != parent_dir]

import datasets as hf_datasets

sys.path = original_sys_path
if original_local_datasets:
    sys.modules["datasets"] = original_local_datasets

from training.train import run_training_pipeline

def main():
    best_params_path = project_root / "experiments" / "best_hyperparameters.json"
    if not best_params_path.exists():
        print(f"Error: {best_params_path} not found. Run optimization first.")
        sys.exit(1)
        
    with open(best_params_path, "r", encoding="utf-8") as f:
        best_params = json.load(f)
        
    print("\n=== Retraining Final Optimized CodeBERT Model ===")
    print(f"Hyperparameters: {json.dumps(best_params, indent=2)}")
    
    checkpoints_dir = project_root / "experiments" / "exp_claudios_codebert-base_42" / "checkpoints"
    temp_retrain_dir = checkpoints_dir / "temp_retrain"
    
    # Ensure empty temp retrain directory
    if temp_retrain_dir.exists():
        shutil.rmtree(temp_retrain_dir)
    temp_retrain_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        run_results = run_training_pipeline(
            backbone="claudios/codebert-base",
            seed=42,
            quick_train=False,
            loss_name="cross_entropy",
            learning_rate=best_params["learning_rate"],
            batch_size=int(best_params["batch_size"]),
            weight_decay=best_params["weight_decay"],
            warmup_ratio=best_params["warmup_ratio"],
            max_len=int(best_params["max_len"]),
            dropout=best_params["dropout"],
            label_smoothing=best_params["label_smoothing"],
            epochs=5,
            save_checkpoints=True,
            checkpoint_dir=temp_retrain_dir
        )
        print("\n=== Retraining Completed Successfully ===")
        print(f"Evaluation metrics: {json.dumps(run_results['metrics'], indent=2)}")
        
        # Save optimized metrics to a separate file for comparison
        opt_metrics_path = project_root / "experiments" / "optimized_eval_metrics.json"
        with open(opt_metrics_path, "w", encoding="utf-8") as f:
            json.dump(run_results['metrics'], f, indent=2)
            
        # Copy newly generated checkpoints to main checkpoints directory
        print("Copying newly trained checkpoints to main checkpoints directory...")
        for ckpt_file in ["checkpoint_best.pt", "checkpoint_last.pt"]:
            src_file = temp_retrain_dir / ckpt_file
            dest_file = checkpoints_dir / ckpt_file
            
            # Archive the previous checkpoint in checkpoints if it exists
            if dest_file.exists():
                archive_name = dest_file.stem + "_150s" + dest_file.suffix
                archive_path = checkpoints_dir / archive_name
                if archive_path.exists():
                    os.remove(archive_path)
                os.rename(dest_file, archive_path)
                print(f"Archived previous checkpoint to {archive_name}")
                
            if src_file.exists():
                shutil.copy2(src_file, dest_file)
                print(f"Copied {ckpt_file} successfully.")
                
    finally:
        # Clean up temp retrain directory
        if temp_retrain_dir.exists():
            print("Cleaning up temporary training directory...")
            shutil.rmtree(temp_retrain_dir)

if __name__ == "__main__":
    main()
