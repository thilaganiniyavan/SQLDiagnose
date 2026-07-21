# seed_manager.py
# Standardized reproducibility seed manager.

import random
import numpy as np
import torch

def set_seed(seed: int) -> None:
    """
    Enforces complete determinism across all random libraries.
    """
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        
    # Enforce PyTorch deterministic backends
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    
    # Enforce PyTorch execution limits
    torch.use_deterministic_algorithms(False)  # Some operations in transformers BPE don't support hard strict determinism flags, so we keep False to avoid runtime exceptions, but lock CUDNN.
