# optimizer.py
# Clean Architecture: Use Case Layer / Interface Adapter
# Custom optimizers, schedules, and learning rate warmups.

import torch.optim as optim
from transformers import get_scheduler
from typing import Dict, Any, Tuple

def configure_optimizers(model, learning_rate: float, weight_decay: float) -> optim.Optimizer:
    """
    Sets up weight decay exclusions (e.g. no weight decay for bias and LayerNorm layers)
    and returns AdamW optimizer instance.
    """
    # Weight decay exclusions for LayerNorm and biases
    no_decay = ["bias", "LayerNorm.weight"]
    optimizer_grouped_parameters = [
        {
            "params": [p for n, p in model.named_parameters() if not any(nd in n for nd in no_decay)],
            "weight_decay": weight_decay,
        },
        {
            "params": [p for n, p in model.named_parameters() if any(nd in n for nd in no_decay)],
            "weight_decay": 0.0,
        },
    ]
    return optim.AdamW(optimizer_grouped_parameters, lr=learning_rate)

def configure_scheduler(
    optimizer, num_warmup_steps: int, num_training_steps: int, scheduler_type: str = "linear"
):
    """
    Builds a linear or cosine schedule with warmup steps.
    """
    return get_scheduler(
        name=scheduler_type,
        optimizer=optimizer,
        num_warmup_steps=num_warmup_steps,
        num_training_steps=num_training_steps
    )
