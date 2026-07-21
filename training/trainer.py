# trainer.py
# Clean Architecture: Use Case Layer
# Orchestrates training and validation epoch iterations.

import torch
import numpy as np
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from torch.utils.tensorboard import SummaryWriter
from training.losses import get_loss_function
from training.optimizer import configure_optimizers, configure_scheduler
from training.checkpoint_manager import CheckpointManager

class SQLClassifierTrainer:
    def __init__(
        self,
        model,
        train_loader,
        val_loader,
        epochs: int,
        learning_rate: float,
        weight_decay: float,
        warmup_ratio: float,
        max_grad_norm: float,
        gradient_accumulation_steps: int,
        device: str,
        loss_name: str,
        checkpoint_dir: Path,
        tb_log_dir: Path,
        early_stopping_patience: int = 3,
        early_stopping_min_delta: float = 0.001,
        save_checkpoints: bool = True,
        label_smoothing: float = 0.0
    ):
        self.model = model
        self.train_loader = train_loader
        self.val_loader = val_loader
        self.epochs = epochs
        self.learning_rate = learning_rate
        self.weight_decay = weight_decay
        self.warmup_ratio = warmup_ratio
        self.max_grad_norm = max_grad_norm
        self.gradient_accumulation_steps = gradient_accumulation_steps
        self.device = device
        self.checkpoint_dir = checkpoint_dir
        
        # Configure optimizer and loss
        self.optimizer = configure_optimizers(self.model.model, learning_rate, weight_decay)
        self.loss_fn = get_loss_function(loss_name, label_smoothing=label_smoothing)
        
        # Compute training steps for scheduler
        num_update_steps_per_epoch = len(self.train_loader) // gradient_accumulation_steps
        num_update_steps_per_epoch = max(num_update_steps_per_epoch, 1)
        self.num_training_steps = epochs * num_update_steps_per_epoch
        num_warmup_steps = int(self.num_training_steps * warmup_ratio)
        self.scheduler = configure_scheduler(self.optimizer, num_warmup_steps, self.num_training_steps)
        
        # Managers
        self.save_checkpoints = save_checkpoints
        self.checkpoint_manager = CheckpointManager(checkpoint_dir) if save_checkpoints else None
        self.writer = SummaryWriter(log_dir=str(tb_log_dir))
        
        # Mixed precision
        self.scaler = torch.cuda.amp.GradScaler(enabled=(device == "cuda"))
        
        # Early Stopping
        self.patience = early_stopping_patience
        self.min_delta = early_stopping_min_delta
        self.best_loss = float("inf")
        self.patience_counter = 0

    def train(self, seed: int) -> List[Dict[str, Any]]:
        """
        Runs training loop across epochs.
        """
        self.model.model.to(self.device)
        history = []
        start_epoch = 1
        
        # Check for checkpoint to resume
        if self.checkpoint_manager:
            checkpoint_path = self.checkpoint_dir / "checkpoint_last.pt"
            if checkpoint_path.exists():
                print(f"Resuming training from checkpoint: {checkpoint_path}")
                checkpoint_state = self.checkpoint_manager.load_checkpoint(
                    checkpoint_path, self.model, self.optimizer, self.scheduler
                )
                start_epoch = checkpoint_state["epoch"] + 1
                
                # Load best loss from best checkpoint if it exists
                best_checkpoint_path = self.checkpoint_dir / "checkpoint_best.pt"
                if best_checkpoint_path.exists():
                    try:
                        best_state = torch.load(best_checkpoint_path, map_location="cpu")
                        self.best_loss = best_state.get("val_metric", float("inf"))
                    except Exception:
                        self.best_loss = checkpoint_state.get("val_metric", float("inf"))
                else:
                    self.best_loss = checkpoint_state.get("val_metric", float("inf"))
                    
                # Load training history if it exists
                history_path = self.checkpoint_dir.parent / "metrics" / "train_history.json"
                if history_path.exists():
                    try:
                        import json
                        with open(history_path, "r", encoding="utf-8") as f:
                            history = json.load(f)
                    except Exception:
                        pass
                        
        for epoch in range(start_epoch, self.epochs + 1):
            self.model.model.train()
            train_loss = 0.0
            
            for step, batch in enumerate(self.train_loader):
                input_ids = batch["input_ids"].to(self.device)
                attention_mask = batch["attention_mask"].to(self.device)
                labels = batch["labels"].to(self.device)
                
                # Forward pass with AMP autocast
                with torch.cuda.amp.autocast(enabled=(self.device == "cuda")):
                    outputs = self.model.model(input_ids=input_ids, attention_mask=attention_mask)
                    logits = outputs.logits
                    loss = self.loss_fn(logits, labels)
                    # Normalize loss if using accumulation steps
                    loss = loss / self.gradient_accumulation_steps
                    
                # Backward pass
                self.scaler.scale(loss).backward()
                
                if (step + 1) % self.gradient_accumulation_steps == 0 or (step + 1) == len(self.train_loader):
                    # Gradient clipping
                    self.scaler.unscale_(self.optimizer)
                    torch.nn.utils.clip_grad_norm_(self.model.model.parameters(), self.max_grad_norm)
                    
                    self.scaler.step(self.optimizer)
                    self.scaler.update()
                    self.scheduler.step()
                    self.optimizer.zero_grad()
                    
                train_loss += loss.item() * self.gradient_accumulation_steps
                
            avg_train_loss = train_loss / len(self.train_loader)
            
            # Validation epoch run
            avg_val_loss, val_accuracy = self.evaluate()
            
            # Write to Tensorboard
            self.writer.add_scalar("Loss/Train", avg_train_loss, epoch)
            self.writer.add_scalar("Loss/Val", avg_val_loss, epoch)
            self.writer.add_scalar("Accuracy/Val", val_accuracy, epoch)
            
            print(f"Epoch {epoch}/{self.epochs} - Train Loss: {avg_train_loss:.4f} | Val Loss: {avg_val_loss:.4f} | Val Acc: {val_accuracy:.4f}")
            
            epoch_metrics = {
                "epoch": epoch,
                "train_loss": avg_train_loss,
                "val_loss": avg_val_loss,
                "val_accuracy": val_accuracy
            }
            history.append(epoch_metrics)
            
            # Save checkpoint (skipped when save_checkpoints=False)
            if self.save_checkpoints and self.checkpoint_manager:
                self.checkpoint_manager.save_checkpoint(
                    self.model, self.optimizer, self.scheduler, epoch, avg_val_loss, seed
                )
            
            # Check for best model
            if avg_val_loss < self.best_loss - self.min_delta:
                self.best_loss = avg_val_loss
                self.patience_counter = 0
                # Save best checkpoint (skipped when save_checkpoints=False)
                if self.save_checkpoints and self.checkpoint_manager:
                    self.checkpoint_manager.save_checkpoint(
                        self.model, self.optimizer, self.scheduler, epoch, avg_val_loss, seed, filename="checkpoint_best.pt"
                    )
            else:
                self.patience_counter += 1
                
            if self.patience_counter >= self.patience:
                print(f"Early stopping triggered at epoch {epoch}")
                break
                
        self.writer.close()
        return history

    def evaluate(self) -> Tuple[float, float]:
        """
        Runs validation evaluation. Returns (val_loss, val_accuracy).
        """
        self.model.model.eval()
        val_loss = 0.0
        correct = 0
        total = 0
        
        with torch.no_grad():
            for batch in self.val_loader:
                input_ids = batch["input_ids"].to(self.device)
                attention_mask = batch["attention_mask"].to(self.device)
                labels = batch["labels"].to(self.device)
                
                outputs = self.model.model(input_ids=input_ids, attention_mask=attention_mask)
                logits = outputs.logits
                loss = self.loss_fn(logits, labels)
                
                val_loss += loss.item()
                preds = torch.argmax(logits, dim=-1)
                correct += (preds == labels).sum().item()
                total += labels.size(0)
                
        avg_val_loss = val_loss / len(self.val_loader)
        accuracy = correct / total if total > 0 else 0.0
        return avg_val_loss, accuracy
