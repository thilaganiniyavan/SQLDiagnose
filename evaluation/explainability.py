# explainability.py
# Clean Architecture: Use Case Layer
# Implements Attention visualization and Integrated Gradients (IG) for transformer models.

import torch
import torch.nn as nn
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from typing import Dict, Any, List, Tuple

def get_embeddings_layer(model: nn.Module) -> nn.Module:
    """
    Locates the word embeddings layer in the model dynamically.
    """
    if hasattr(model, "distilbert"):
        return model.distilbert.embeddings.word_embeddings
    elif hasattr(model, "bert"):
        return model.bert.embeddings.word_embeddings
    elif hasattr(model, "roberta"):
        return model.roberta.embeddings.word_embeddings
    else:
        # Fallback search
        for module in model.modules():
            if isinstance(module, nn.Embedding):
                return module
    raise ValueError("Could not find Embedding layer in model.")

def compute_integrated_gradients(
    model: nn.Module,
    input_ids: torch.Tensor,
    attention_mask: torch.Tensor,
    target_class: int,
    steps: int = 50
) -> Tuple[np.ndarray, int]:
    """
    Computes Integrated Gradients attribution scores for each input token.
    Returns (attributions, predicted_class).
    """
    model.eval()
    device = next(model.parameters()).device
    
    # 1. Retrieve the embedding layer
    embeddings_layer = get_embeddings_layer(model)
    
    # 2. Get input and baseline embeddings
    input_embeds = embeddings_layer(input_ids.to(device)).clone().detach()
    
    # Baseline: all pad or zero tokens
    pad_token_id = 0
    baseline_ids = torch.full_like(input_ids, pad_token_id, device=device)
    baseline_embeds = embeddings_layer(baseline_ids).clone().detach()
    
    # 3. Predict class
    outputs = model(input_ids=input_ids.to(device), attention_mask=attention_mask.to(device))
    logits = outputs.logits
    pred_class = torch.argmax(logits, dim=-1).item()
    
    if target_class is None:
        target_class = pred_class
        
    # 4. Integrate gradients
    grads = []
    alphas = np.linspace(0, 1, steps)
    
    for alpha in alphas:
        # Linearly interpolate embeddings
        interpolated = baseline_embeds + alpha * (input_embeds - baseline_embeds)
        interpolated = interpolated.clone().detach().requires_grad_(True)
        
        # Forward pass using inputs_embeds
        out = model(inputs_embeds=interpolated, attention_mask=attention_mask.to(device))
        score = out.logits[0, target_class]
        
        # Backward pass
        model.zero_grad()
        score.backward()
        
        grads.append(interpolated.grad.cpu().detach().numpy())
        
    # Riemann sum approximation
    avg_grads = np.mean(grads, axis=0)  # shape (1, seq_len, embed_dim)
    delta = (input_embeds - baseline_embeds).cpu().detach().numpy()  # shape (1, seq_len, embed_dim)
    attributions = avg_grads * delta  # shape (1, seq_len, embed_dim)
    
    # Sum across the embedding dimensions
    attributions = np.sum(attributions, axis=-1).squeeze(0)  # shape (seq_len,)
    
    return attributions, pred_class

def explain_query(
    model: nn.Module,
    tokenizer: Any,
    query: str,
    target_class: int = None,
    max_len: int = 128,
    save_dir: Path = None
) -> Dict[str, Any]:
    """
    Orchestrates the XAI explanation pipeline for a single SQL query.
    Extracts attention weights, computes IG attribution, plots, and returns metrics.
    """
    device = next(model.parameters()).device
    
    # Tokenize input query
    inputs = tokenizer(
        query,
        add_special_tokens=True,
        max_length=max_len,
        padding="max_length",
        truncation=True,
        return_attention_mask=True,
        return_tensors="pt"
    )
    
    input_ids = inputs["input_ids"].to(device)
    attention_mask = inputs["attention_mask"].to(device)
    
    # Get token strings for labeling plots
    tokens = tokenizer.convert_ids_to_tokens(input_ids[0].cpu().tolist())
    
    # Filter out padding tokens to make plots readable
    valid_len = int(torch.sum(attention_mask[0]).item())
    tokens = tokens[:valid_len]
    
    # 1. Compute Integrated Gradients
    attributions, pred_class = compute_integrated_gradients(
        model, input_ids, attention_mask, target_class, steps=50
    )
    attributions = attributions[:valid_len]
    
    # 2. Extract self-attentions (forward pass with output_attentions=True)
    model.eval()
    with torch.no_grad():
        outputs = model(
            input_ids=input_ids,
            attention_mask=attention_mask,
            output_attentions=True
        )
        logits = outputs.logits
        probs = torch.softmax(logits, dim=-1)[0].cpu().tolist()
        attentions = outputs.attentions  # tuple of length num_layers
        
    # Extract last-layer mean self-attention
    # Shape: (num_heads, seq_len, seq_len)
    last_attention = attentions[-1][0]
    mean_attention = torch.mean(last_attention, dim=0).cpu().numpy()[:valid_len, :valid_len]
    
    # 3. Create Plots if save_dir is specified
    if save_dir:
        save_dir.mkdir(parents=True, exist_ok=True)
        
        # 3.1 Attention Heatmap Plot
        plt.figure(figsize=(10, 8))
        sns.heatmap(
            mean_attention,
            xticklabels=tokens,
            yticklabels=tokens,
            cmap="viridis",
            annot=False
        )
        plt.title(f"Self-Attention Heatmap (Last Layer Average)\nQuery Class: {pred_class}", fontsize=13, fontweight="bold")
        plt.xticks(rotation=45, ha="right", fontsize=9)
        plt.yticks(fontsize=9)
        plt.tight_layout()
        plt.savefig(save_dir / "xai_attention_heatmap.png", dpi=150)
        plt.close()
        
        # 3.2 Token Importance Attribution Plot (IG)
        plt.figure(figsize=(10, 6))
        # Color code: Teal for positive attribution, Orange for negative
        colors = ["#2b8cbe" if attr >= 0 else "#de2d26" for attr in attributions]
        
        # Plot bar chart
        plt.bar(range(len(tokens)), attributions, color=colors, edgecolor="grey", alpha=0.95)
        plt.xticks(range(len(tokens)), tokens, rotation=45, ha="right", fontsize=9)
        plt.axhline(0, color="black", lw=1, ls="--")
        plt.ylabel("Attribution Score", fontsize=11)
        plt.title(f"Feature Attribution (Integrated Gradients)\nPredicted Class: {pred_class} | Confidence: {probs[pred_class]*100:.1f}%", fontsize=13, fontweight="bold")
        plt.tight_layout()
        plt.savefig(save_dir / "xai_token_importance.png", dpi=150)
        plt.close()
        
    return {
        "tokens": tokens,
        "attributions": attributions.tolist(),
        "attention_map": mean_attention.tolist(),
        "probabilities": probs,
        "predicted_class": pred_class
    }
