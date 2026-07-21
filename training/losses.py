# losses.py
# Clean Architecture: Use Case Layer / Interface Adapter
# Contains standard or custom loss functions suitable for multi-class SQL error classification.

import torch
import torch.nn as nn
import torch.nn.functional as F

class FocalLoss(nn.Module):
    """
    Computes Focal Loss for addressing class imbalance.
    """
    def __init__(self, alpha: float = 1.0, gamma: float = 2.0, reduction: str = 'mean'):
        super(FocalLoss, self).__init__()
        self.alpha = alpha
        self.gamma = gamma
        self.reduction = reduction

    def forward(self, logits, targets):
        ce_loss = F.cross_entropy(logits, targets, reduction='none')
        pt = torch.exp(-ce_loss)
        focal_loss = self.alpha * ((1 - pt) ** self.gamma) * ce_loss
        
        if self.reduction == 'mean':
            return focal_loss.mean()
        elif self.reduction == 'sum':
            return focal_loss.sum()
        return focal_loss

def get_loss_function(loss_name: str, class_weights = None, label_smoothing: float = 0.0) -> nn.Module:
    """
    Factory function returning loss instances based on configurations.
    """
    if loss_name.lower() == "focal":
        return FocalLoss()
    else:
        # Default to standard cross entropy loss
        if class_weights is not None:
            weights_tensor = torch.tensor(class_weights, dtype=torch.float)
            return nn.CrossEntropyLoss(weight=weights_tensor, label_smoothing=label_smoothing)
        return nn.CrossEntropyLoss(label_smoothing=label_smoothing)
