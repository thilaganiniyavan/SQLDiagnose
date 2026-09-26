# explainability.py
# Token-level explanations for the transformer classifier.
#
#   method="gxi" - gradient x input: one backward pass, fast enough for interactive use.
#   method="ig"  - integrated gradients (Sundararajan et al., 2017) with a padding-token baseline,
#                  computed in one batched forward/backward pass over all interpolation steps.
#
# Attributions are returned for the query segment (the part a user can act on) and for the
# schema segment separately, merged from sub-word pieces back to whole words.

from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import torch
import torch.nn as nn


def _embedding_layer(model: nn.Module) -> nn.Module:
    return model.get_input_embeddings()


def _attributions(model, input_ids, attention_mask, target: int, method: str, steps: int) -> torch.Tensor:
    emb_layer = _embedding_layer(model)
    with torch.no_grad():
        inputs = emb_layer(input_ids)
    if method == "gxi":
        x = inputs.clone().requires_grad_(True)
        score = model(inputs_embeds=x, attention_mask=attention_mask).logits[0, target]
        grad, = torch.autograd.grad(score, x)
        return (grad * inputs).sum(-1)[0]
    pad_id = getattr(model.config, "pad_token_id", None) or 1
    baseline_ids = torch.where(attention_mask.bool(), torch.full_like(input_ids, pad_id), input_ids)
    # keep special tokens at both ends so the baseline is still a well-formed sequence
    baseline_ids[:, 0] = input_ids[:, 0]
    last = int(attention_mask.sum()) - 1
    baseline_ids[:, last] = input_ids[:, last]
    with torch.no_grad():
        baseline = emb_layer(baseline_ids)
    alphas = torch.linspace(1.0 / steps, 1.0, steps, device=inputs.device).view(-1, 1, 1)
    path = (baseline + alphas * (inputs - baseline)).detach().requires_grad_(True)
    mask = attention_mask.expand(steps, -1)
    scores = model(inputs_embeds=path, attention_mask=mask).logits[:, target].sum()
    grads, = torch.autograd.grad(scores, path)
    return (grads.mean(0, keepdim=True) * (inputs - baseline)).sum(-1)[0]


def _merge_pieces(tokenizer, ids: Sequence[int], scores: Sequence[float]) -> List[Tuple[str, float]]:
    """Merges byte-level BPE pieces into words (a piece starting with 'Ġ' begins a new word)."""
    words: List[Tuple[str, float]] = []
    for tid, s in zip(ids, scores):
        piece = tokenizer.convert_ids_to_tokens(int(tid))
        text = tokenizer.convert_tokens_to_string([piece])
        starts_word = piece.startswith("Ġ") or piece.startswith("▁") or not words or not text[:1].isalnum() \
            or not words[-1][0][-1:].isalnum()
        if starts_word:
            words.append((text.strip(), s))
        else:
            w, ws = words[-1]
            words[-1] = (w + text.strip(), ws + s)
    return [(w, s) for w, s in words if w]


def integrated_gradients(model, tokenizer, encoding: Dict[str, torch.Tensor], labels: Sequence[str],
                         steps: int = 32, device="cpu", method: str = "ig", target: int = None) -> Dict:
    model.eval()
    input_ids = encoding["input_ids"].to(device)
    attention_mask = encoding["attention_mask"].to(device)
    with torch.no_grad():
        probs = torch.softmax(model(input_ids=input_ids, attention_mask=attention_mask).logits, -1)[0]
    if target is None:
        target = int(probs.argmax())
    scores = _attributions(model, input_ids, attention_mask, target, method, steps).detach().cpu()

    ids = input_ids[0].cpu().tolist()
    n = int(attention_mask.sum())
    special = set(tokenizer.all_special_ids)
    # segment boundary: text pairs are encoded as <s> A </s></s> B </s>
    sep = tokenizer.sep_token_id
    first_sep = next((i for i in range(1, n) if ids[i] == sep), n)
    query_idx = [i for i in range(1, first_sep) if ids[i] not in special]
    schema_idx = [i for i in range(first_sep, n) if ids[i] not in special]
    total = float(scores[:n].abs().sum()) or 1.0

    def seg(idx):
        return [{"token": w, "score": round(s / total, 5)}
                for w, s in _merge_pieces(tokenizer, [ids[i] for i in idx], [float(scores[i]) for i in idx])]

    return {
        "target_class": labels[target],
        "method": "integrated_gradients" if method == "ig" else "gradient_x_input",
        "query_tokens": seg(query_idx),
        "schema_tokens": seg(schema_idx),
        "probability": float(probs[target]),
    }


def plot_token_attributions(tokens: List[Dict], title: str, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    words = [t["token"] for t in tokens]
    vals = [t["score"] for t in tokens]
    fig, ax = plt.subplots(figsize=(max(6, 0.45 * len(words)), 3.2))
    ax.bar(range(len(words)), vals, color=["#2a78c2" if v >= 0 else "#d1495b" for v in vals])
    ax.axhline(0, color="#888", lw=0.8)
    ax.set_xticks(range(len(words)))
    ax.set_xticklabels(words, rotation=60, ha="right", fontsize=8)
    ax.set_ylabel("attribution")
    ax.set_title(title, fontsize=10)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
