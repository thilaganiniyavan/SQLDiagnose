# train.py
# Clean Architecture: Use Case Layer
# Main orchestrator for training the transformer classifier.

import torch
import pandas as pd
import yaml
import json
from pathlib import Path
from typing import Dict, Any, List

from utils.logger import setup_logger
from utils.config_loader import load_yaml_config, get_full_config
from utils.seed_manager import set_seed
from datasets.dataloader import SQLClassificationDataset, create_data_loaders
from models.tokenizer_factory import SQLTokenizerFactory
from models.model_factory import SQLModelFactory
from training.trainer import SQLClassifierTrainer
from evaluation.evaluate import run_evaluation_pipeline
from experiments.experiment_manager import ExperimentManager

def run_training_pipeline(
    backbone: str,
    seed: int,
    quick_train: bool = True,
    loss_name: str = "cross_entropy",
    learning_rate: float = None,
    batch_size: int = None,
    weight_decay: float = None,
    warmup_ratio: float = None,
    max_len: int = None,
    dropout: float = None,
    label_smoothing: float = 0.0,
    epochs: int = None,
    save_checkpoints: bool = None,
    checkpoint_dir: Path = None
) -> Dict[str, Any]:
    """
    Bootstrap script loading yaml configs, datasets, instantiating 
    components, and executing the ModelTrainer.
    """
    project_root = Path(__file__).parent.parent
    configs_dir = project_root / "configs"
    
    # Load combined config
    config = get_full_config(configs_dir)
    
    # Override seed and backbone from args
    config["training"]["training"]["seed"] = seed
    config["model"]["model"]["backbone"] = backbone
    
    # Setup Experiment Tracking early to get deterministic path
    exp_manager = ExperimentManager(project_root / "experiments", backbone, seed)
    exp_manager.capture_env_metadata(seed, config["training"])
    
    # Configure logging directly in the experiment directory
    log_file = exp_manager.exp_dir / "train.log"
    logger = setup_logger("train_pipeline", str(log_file))
    logger.info(f"Initializing training for model: {backbone} | seed: {seed}")
    
    # Set seed
    set_seed(seed)
    
    # Load dataset
    processed_dir = project_root / "datasets" / "processed"
    train_df = pd.read_csv(processed_dir / "dataset_train.csv")
    val_df = pd.read_csv(processed_dir / "dataset_validation.csv")
    
    # Map error type to integers
    class_mapping = {
        "MISSING_COMMA": 1,
        "MISSING_FROM": 1,
        "PARENTHESES_MISMATCH": 1,
        "RESERVED_KEYWORD_MISUSE": 1,
        "INCORRECT_WHERE": 1,
        "UNKNOWN_TABLE": 2,
        "UNKNOWN_COLUMN": 3,
        "DATATYPE_MISMATCH": 4,
        "DUPLICATE_ALIAS": 5,
        "PERMISSION_DENIED": 6,
        "WRONG_JOIN": 7,
        "MISSING_JOIN_CONDITION": 7,
        "WRONG_GROUPBY": 7,
        "AGGREGATE_MISUSE": 7,
        "WRONG_ALIAS": 7,
        "HAVING_MISUSE": 7,
        "ORDERBY_MISUSE": 7,
        "LIMIT_MISUSE": 7,
        "NESTED_QUERY_MISTAKE": 7,
        "FUNCTION_MISUSE": 7,
        "NULL_COMPARISON_ERRORS": 7,
        "CORRECT": 0
    }
    
    train_df["label"] = train_df["error_type"].map(class_mapping)
    val_df["label"] = val_df["error_type"].map(class_mapping)
    
    # Quick train settings to prevent CPU/GPU execution timeout
    if quick_train:
        logger.info("Quick train enabled. Sub-sampling data to verify execution pipeline.")
        train_df = train_df.sample(50, random_state=seed)
        val_df = val_df.sample(20, random_state=seed)
        epochs = 1
    else:
        epochs = epochs if epochs is not None else config["training"]["training"].get("epochs", 5)
        
    train_queries = train_df["sql_query"].tolist()
    train_labels = train_df["label"].tolist()
    val_queries = val_df["sql_query"].tolist()
    val_labels = val_df["label"].tolist()
    
    # Setup Factories
    logger.info("Loading Tokenizer and Model adapters...")
    tokenizer_factory = SQLTokenizerFactory()
    model_factory = SQLModelFactory()
    
    tokenizer = tokenizer_factory.get_tokenizer(backbone)
    
    # Set model config parameters
    dropout_val = dropout if dropout is not None else float(config["model"]["model"].get("dropout", 0.1))
    model = model_factory.get_model(
        model_name_or_path=backbone,
        num_labels=config["model"]["model"].get("num_labels", 8),
        attention_dropout=dropout_val,
        hidden_dropout=dropout_val
    )
    
    # Create datasets
    max_len = max_len if max_len is not None else config["model"]["model"].get("max_sequence_length", 256)
    batch_size = batch_size if batch_size is not None else config["training"]["training"].get("batch_size", 16)
    
    train_dataset = SQLClassificationDataset(train_queries, train_labels, tokenizer.tokenizer, max_len)
    val_dataset = SQLClassificationDataset(val_queries, val_labels, tokenizer.tokenizer, max_len)
    
    train_loader = torch.utils.data.DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = torch.utils.data.DataLoader(val_dataset, batch_size=batch_size, shuffle=False)
    
    # ExperimentManager already initialized early
    
    # Trainer
    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"Using execution device: {device}")
    
    lr = learning_rate if learning_rate is not None else float(config["training"]["training"].get("learning_rate", 3e-5))
    wd = weight_decay if weight_decay is not None else float(config["training"]["training"].get("weight_decay", 0.01))
    wr = warmup_ratio if warmup_ratio is not None else float(config["training"]["optimizer"].get("warmup_ratio", 0.1))
    
    trainer = SQLClassifierTrainer(
        model=model,
        train_loader=train_loader,
        val_loader=val_loader,
        epochs=epochs,
        learning_rate=lr,
        weight_decay=wd,
        warmup_ratio=wr,
        max_grad_norm=float(config["training"]["training"].get("max_grad_norm", 1.0)),
        gradient_accumulation_steps=1,
        device=device,
        loss_name=loss_name,
        checkpoint_dir=checkpoint_dir if checkpoint_dir is not None else exp_manager.checkpoints_dir,
        tb_log_dir=exp_manager.tb_dir,
        early_stopping_patience=config["training"]["training"]["early_stopping"].get("patience", 3),
        early_stopping_min_delta=config["training"]["training"]["early_stopping"].get("min_delta", 0.001),
        save_checkpoints=save_checkpoints if save_checkpoints is not None else (not quick_train),  # Disable checkpoints in quick_train to save disk space
        label_smoothing=label_smoothing
    )
    
    logger.info("Starting model training run...")
    import time
    start_time = time.time()
    history = trainer.train(seed)
    training_time = time.time() - start_time
    logger.info(f"Model training run complete in {training_time:.2f} seconds.")
    
    # Run evaluation pipeline
    logger.info("Executing evaluation pipeline...")
    classes = [config["model"]["classes"][k] for k in sorted(config["model"]["classes"].keys())]
    eval_results = run_evaluation_pipeline(
        model=model,
        test_loader=val_loader,
        device=device,
        classes=classes,
        report_dir=exp_manager.plots_dir
    )
    
    # Record metadata metrics
    eval_metrics = eval_results["metrics"]
    eval_metrics["training_time_seconds"] = training_time
    eval_metrics["parameter_count"] = sum(p.numel() for p in model.model.parameters())
    eval_metrics["model_size_mb"] = sum(p.numel() * p.element_size() for p in model.model.parameters()) / (1024 * 1024)
    
    exp_manager.save_run_metrics(history, eval_metrics)
    
    return {
        "exp_dir": exp_manager.exp_dir,
        "metrics": eval_metrics,
        "plots_dir": exp_manager.plots_dir
    }

if __name__ == "__main__":
    # Standard single model launch entrypoint
    run_training_pipeline(
        backbone="distilbert-base-uncased",
        seed=42,
        quick_train=True
    )
