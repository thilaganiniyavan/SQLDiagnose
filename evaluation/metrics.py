# metrics.py
# Classification metrics, statistical tests and figures used by evaluation/evaluate.py.

import math
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support,
                             roc_auc_score)

PALETTE = ["#2a78c2", "#e8833a", "#3aa57a", "#c2413b", "#8a63c9", "#8c6d4f", "#d36fb4", "#7f7f7f"]


def classification_metrics(y_true: Sequence[int], y_pred: Sequence[int], labels: List[str],
                           probs: Optional[np.ndarray] = None) -> Dict:
    idx = list(range(len(labels)))
    p, r, f, s = precision_recall_fscore_support(y_true, y_pred, labels=idx, zero_division=0)
    out = {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "macro_precision": float(np.mean(p)),
        "macro_recall": float(np.mean(r)),
        "macro_f1": float(f1_score(y_true, y_pred, labels=idx, average="macro", zero_division=0)),
        "per_class": {labels[i]: {"precision": float(p[i]), "recall": float(r[i]), "f1": float(f[i]),
                                  "support": int(s[i])} for i in idx},
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=idx).tolist(),
    }
    if probs is not None:
        try:
            out["macro_roc_auc"] = float(roc_auc_score(y_true, probs, multi_class="ovr", labels=idx))
        except ValueError:
            out["macro_roc_auc"] = None
        out["ece"] = expected_calibration_error(y_true, probs)
    return out


def expected_calibration_error(y_true: Sequence[int], probs: np.ndarray, bins: int = 15) -> float:
    conf = probs.max(1)
    pred = probs.argmax(1)
    correct = (pred == np.asarray(y_true)).astype(float)
    edges = np.linspace(0, 1, bins + 1)
    ece = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf > lo) & (conf <= hi)
        if m.any():
            ece += m.mean() * abs(correct[m].mean() - conf[m].mean())
    return float(ece)


def bootstrap_ci(y_true: Sequence[int], y_pred: Sequence[int], n_labels: int, n: int = 1000,
                 seed: int = 0) -> Dict[str, List[float]]:
    rng = np.random.default_rng(seed)
    y_true, y_pred = np.asarray(y_true), np.asarray(y_pred)
    accs, f1s = [], []
    for _ in range(n):
        i = rng.integers(0, len(y_true), len(y_true))
        accs.append(accuracy_score(y_true[i], y_pred[i]))
        f1s.append(f1_score(y_true[i], y_pred[i], labels=list(range(n_labels)), average="macro", zero_division=0))
    return {"accuracy": [float(np.percentile(accs, 2.5)), float(np.percentile(accs, 97.5))],
            "macro_f1": [float(np.percentile(f1s, 2.5)), float(np.percentile(f1s, 97.5))]}


def mcnemar_exact(correct_a: Sequence[bool], correct_b: Sequence[bool]) -> Dict[str, float]:
    """Exact (binomial) McNemar test on paired correctness."""
    a, b = np.asarray(correct_a), np.asarray(correct_b)
    only_a = int(np.sum(a & ~b))
    only_b = int(np.sum(~a & b))
    n = only_a + only_b
    if n == 0:
        return {"only_a": only_a, "only_b": only_b, "p_value": 1.0}
    k = min(only_a, only_b)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return {"only_a": only_a, "only_b": only_b, "p_value": float(min(1.0, 2 * p))}


# ---------------------------------------------------------------------- figures
def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False})
    return plt


def plot_confusion(cm: List[List[int]], labels: List[str], title: str, path: Path) -> None:
    plt = _plt()
    cm = np.asarray(cm, dtype=float)
    norm = cm / np.maximum(cm.sum(1, keepdims=True), 1)
    fig, ax = plt.subplots(figsize=(6.4, 5.4))
    im = ax.imshow(norm, cmap="Blues", vmin=0, vmax=1)
    short = [l.replace("_", "\n") for l in labels]
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(short, fontsize=7)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(short, fontsize=7)
    for i in range(len(labels)):
        for j in range(len(labels)):
            if cm[i, j]:
                ax.text(j, i, f"{int(cm[i, j])}", ha="center", va="center", fontsize=7,
                        color="white" if norm[i, j] > 0.55 else "#1f2937")
    ax.set_xlabel("predicted")
    ax.set_ylabel("true")
    ax.set_title(title)
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label="row-normalised")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def plot_grouped_bars(groups: List[str], series: Dict[str, List[float]], ylabel: str, title: str, path: Path,
                      ylim=(0, 1.15)) -> None:
    plt = _plt()
    fig, ax = plt.subplots(figsize=(max(6, 0.95 * len(groups) + 2), 3.6))
    width = 0.8 / len(series)
    x = np.arange(len(groups))
    for k, (name, vals) in enumerate(series.items()):
        ax.bar(x + (k - (len(series) - 1) / 2) * width, vals, width, label=name, color=PALETTE[k % len(PALETTE)])
    ax.set_xticks(x)
    ax.set_xticklabels([g.replace("_", "\n") for g in groups], fontsize=7)
    ax.set_ylabel(ylabel)
    ax.set_ylim(*ylim)
    ax.set_title(title)
    ax.legend(frameon=False, fontsize=8, ncol=min(4, len(series)))
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def plot_reliability(y_true: Sequence[int], probs: np.ndarray, title: str, path: Path, bins: int = 10) -> None:
    plt = _plt()
    conf = probs.max(1)
    correct = (probs.argmax(1) == np.asarray(y_true)).astype(float)
    edges = np.linspace(0, 1, bins + 1)
    xs, ys, ns = [], [], []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf > lo) & (conf <= hi)
        if m.any():
            xs.append(conf[m].mean())
            ys.append(correct[m].mean())
            ns.append(m.sum())
    fig, ax = plt.subplots(figsize=(4.2, 4))
    ax.plot([0, 1], [0, 1], ls="--", color="#9ca3af", lw=1, label="perfect calibration")
    ax.plot(xs, ys, marker="o", color=PALETTE[0], label="model")
    ax.set_xlabel("confidence")
    ax.set_ylabel("accuracy")
    ax.set_title(title)
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def plot_training_curve(log_csv: Path, path: Path) -> bool:
    import csv
    if not log_csv.exists():
        return False
    rows = list(csv.DictReader(open(log_csv)))
    if not rows:
        return False
    plt = _plt()
    steps = [int(r["step"]) for r in rows]
    fig, ax1 = plt.subplots(figsize=(6, 3.4))
    ax1.plot(steps, [float(r["train_loss"]) for r in rows], color=PALETTE[1], marker="o", label="train loss")
    ax1.plot(steps, [float(r["val_loss"]) for r in rows], color=PALETTE[3], marker="o", label="validation loss")
    ax1.set_xlabel("optimizer step")
    ax1.set_ylabel("loss")
    ax2 = ax1.twinx()
    ax2.plot(steps, [float(r["val_macro_f1"]) for r in rows], color=PALETTE[0], marker="s", label="validation macro-F1")
    ax2.set_ylabel("macro-F1")
    ax2.set_ylim(0, 1)
    ax2.spines["right"].set_visible(True)
    lines = ax1.get_legend_handles_labels()[0] + ax2.get_legend_handles_labels()[0]
    ax1.legend(lines, [l.get_label() for l in lines], frameon=False, fontsize=8, loc="center right")
    ax1.set_title("Fine-tuning curve")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return True
