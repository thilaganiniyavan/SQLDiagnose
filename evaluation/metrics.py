# metrics.py
# Clean Architecture: Interface Adapter / Frameworks & Drivers
# Computes classification metrics and generates graphs.

import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from typing import Dict, List, Any
from sklearn.metrics import classification_report, confusion_matrix, roc_curve, auc, precision_recall_curve
from sklearn.calibration import calibration_curve

def compute_classification_report(y_true: List[int], y_pred: List[int], y_probs: List[List[float]] = None) -> Dict[str, Any]:
    """
    Computes overall F1, precision, recall, top-k accuracy, and per-class reports.
    """
    report = classification_report(y_true, y_pred, output_dict=True, zero_division=0)
    
    # Calculate top-2 and top-3 accuracy if probabilities are available
    top2_acc = 0.0
    top3_acc = 0.0
    if y_probs is not None and len(y_probs) > 0:
        y_true_arr = np.array(y_true)
        y_probs_arr = np.array(y_probs)
        
        # Argsort sorts in ascending order, so we reverse it
        top_k_indices = np.argsort(y_probs_arr, axis=1)[:, ::-1]
        
        top2_hits = np.any(top_k_indices[:, :2] == y_true_arr[:, None], axis=1)
        top2_acc = float(np.mean(top2_hits))
        
        top3_hits = np.any(top_k_indices[:, :3] == y_true_arr[:, None], axis=1)
        top3_acc = float(np.mean(top3_hits))
        
    return {
        "report": report,
        "top2_accuracy": top2_acc,
        "top3_accuracy": top3_acc
    }

def plot_confusion_matrix(y_true: List[int], y_pred: List[int], classes: List[str], save_path: str):
    """
    Generates a heatmapped confusion matrix and saves the PNG artifact.
    """
    cm = confusion_matrix(y_true, y_pred)
    # Normalize confusion matrix
    cm_norm = cm.astype('float') / cm.sum(axis=1)[:, np.newaxis]
    cm_norm = np.nan_to_num(cm_norm) # Replace NaNs with 0
    
    plt.figure(figsize=(10, 8))
    sns.heatmap(cm_norm, annot=True, fmt=".2f", cmap="Blues", xticklabels=classes, yticklabels=classes)
    plt.title("Normalized Confusion Matrix")
    plt.ylabel("True Class")
    plt.xlabel("Predicted Class")
    plt.xticks(rotation=45, ha='right')
    plt.yticks(rotation=0)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150)
    plt.close()

def plot_roc_curves(y_true: List[int], y_probs: List[List[float]], classes: List[str], save_path: str):
    """
    Plots multi-class One-vs-Rest ROC-AUC curves and saves the figure.
    """
    y_true_arr = np.array(y_true)
    y_probs_arr = np.array(y_probs)
    
    n_classes = len(classes)
    plt.figure(figsize=(10, 8))
    
    for i in range(n_classes):
        # Binarize label for current class i
        y_true_binary = (y_true_arr == i).astype(int)
        y_prob_class = y_probs_arr[:, i]
        
        fpr, tpr, _ = roc_curve(y_true_binary, y_prob_class)
        roc_auc = auc(fpr, tpr)
        
        plt.plot(fpr, tpr, label=f'{classes[i]} (AUC = {roc_auc:.2f})')
        
    plt.plot([0, 1], [0, 1], 'k--', label='Random Guess')
    plt.xlim([0.0, 1.0])
    plt.ylim([0.0, 1.05])
    plt.xlabel('False Positive Rate')
    plt.ylabel('True Positive Rate')
    plt.title('Receiver Operating Characteristic (ROC) Curves (One-vs-Rest)')
    plt.legend(loc="lower right")
    plt.grid(True, linestyle=':', alpha=0.6)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150)
    plt.close()

def plot_pr_curves(y_true: List[int], y_probs: List[List[float]], classes: List[str], save_path: str):
    """
    Plots multi-class Precision-Recall curves.
    """
    y_true_arr = np.array(y_true)
    y_probs_arr = np.array(y_probs)
    
    n_classes = len(classes)
    plt.figure(figsize=(10, 8))
    
    for i in range(n_classes):
        y_true_binary = (y_true_arr == i).astype(int)
        y_prob_class = y_probs_arr[:, i]
        
        precision, recall, _ = precision_recall_curve(y_true_binary, y_prob_class)
        plt.plot(recall, precision, label=f'{classes[i]}')
        
    plt.xlabel('Recall')
    plt.ylabel('Precision')
    plt.title('Precision-Recall Curves (One-vs-Rest)')
    plt.legend(loc="lower left")
    plt.grid(True, linestyle=':', alpha=0.6)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150)
    plt.close()

def plot_calibration_curves(y_true: List[int], y_probs: List[List[float]], classes: List[str], save_path: str):
    """
    Plots calibration curves showing how class probability scores match actual frequencies.
    """
    y_true_arr = np.array(y_true)
    y_probs_arr = np.array(y_probs)
    
    n_classes = len(classes)
    plt.figure(figsize=(10, 8))
    
    for i in range(n_classes):
        y_true_binary = (y_true_arr == i).astype(int)
        y_prob_class = y_probs_arr[:, i]
        
        # Only plot if we have positive classes present in validation set
        if np.sum(y_true_binary) > 0:
            prob_true, prob_pred = calibration_curve(y_true_binary, y_prob_class, n_bins=10)
            plt.plot(prob_pred, prob_true, marker='s', label=f'{classes[i]}')
            
    plt.plot([0, 1], [0, 1], 'k--', label='Perfect Calibration')
    plt.xlabel('Mean Predicted Probability')
    plt.ylabel('Fraction of Positives')
    plt.title('Calibration Curves')
    plt.legend(loc="lower right")
    plt.grid(True, linestyle=':', alpha=0.6)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150)
    plt.close()
