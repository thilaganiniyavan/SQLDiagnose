# checkpoint_manager.py
# Reusable checkpoint manager that saves/loads model and optimizer training state dictionary.

import torch
import json
from pathlib import Path
from typing import Dict, Any, Optional

class CheckpointManager:
    def __init__(self, checkpoint_dir: Path):
        self.checkpoint_dir = checkpoint_dir
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def save_checkpoint(
        self,
        model,
        optimizer,
        scheduler,
        epoch: int,
        val_metric: float,
        seed: int,
        filename: str = "checkpoint_last.pt"
    ) -> Path:
        """
        Saves full PyTorch model state and metadata.
        """
        save_path = self.checkpoint_dir / filename
        state = {
            "epoch": epoch,
            "val_metric": val_metric,
            "seed": seed,
            "model_state_dict": model.model.state_dict(),
            "optimizer_state_dict": optimizer.state_dict(),
            "scheduler_state_dict": scheduler.state_dict() if scheduler else None
        }
        torch.save(state, save_path)
        return save_path

    def load_checkpoint(self, checkpoint_path: Path, model, optimizer=None, scheduler=None) -> Dict[str, Any]:
        """
        Loads training state into instances.
        """
        if not checkpoint_path.exists():
            raise FileNotFoundError(f"Checkpoint not found: {checkpoint_path}")
            
        state = torch.load(checkpoint_path, map_location="cpu")
        model.model.load_state_dict(state["model_state_dict"])
        
        if optimizer and state["optimizer_state_dict"]:
            optimizer.load_state_dict(state["optimizer_state_dict"])
        if scheduler and state["scheduler_state_dict"]:
            scheduler.load_state_dict(state["scheduler_state_dict"])
            
        return {
            "epoch": state["epoch"],
            "val_metric": state["val_metric"],
            "seed": state["seed"]
        }
