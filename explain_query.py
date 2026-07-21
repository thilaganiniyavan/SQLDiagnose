# explain_query.py
import argparse
from pathlib import Path
import torch
from models.classifier import TransformerSQLClassifier
from models.tokenizer import TransformerSQLTokenizer
from transformers import AutoTokenizer

def main():
    parser = argparse.ArgumentParser(description="Explain SQL classification using Explainable AI.")
    parser.add_argument(
        "--query",
        type=str,
        default="SELECT name, FROM users WHERE id = 1;",
        help="The SQL query to analyze."
    )
    parser.add_argument(
        "--model",
        type=str,
        default="roberta-base",
        help="The HuggingFace model or path to local checkpoint."
    )
    parser.add_argument(
        "--save_dir",
        type=str,
        default="reports/figures",
        help="Directory to save explanation plots."
    )
    args = parser.parse_args()
    
    print(f"Loading model: {args.model} ...")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    
    # 1. Initialize classifier and tokenizer
    if args.model.endswith(".pt") and Path(args.model).exists():
        print(f"Loading custom state dict checkpoint from: {args.model}")
        base_model = "claudios/codebert-base"
        tokenizer = AutoTokenizer.from_pretrained(base_model)
        classifier = TransformerSQLClassifier(model_name_or_path=base_model, num_labels=8)
        state = torch.load(args.model, map_location="cpu")
        classifier.model.load_state_dict(state["model_state_dict"])
    else:
        classifier = TransformerSQLClassifier(model_name_or_path=args.model, num_labels=8)
        tokenizer = AutoTokenizer.from_pretrained(args.model)
        
    classifier.model.to(device)
    
    print(f"Analyzing query: '{args.query}' on device: {device}")
    
    # 2. Run explanation pipeline
    save_path = Path(args.save_dir)
    explanation = classifier.predict_with_explanation(
        query=args.query,
        tokenizer=tokenizer,
        save_dir=str(save_path)
    )
    
    # 3. Print results
    pred_class = explanation["predicted_class"]
    probs = explanation["probabilities"]
    tokens = explanation["tokens"]
    attributions = explanation["attributions"]
    
    error_categories = [
        "CORRECT",
        "SYNTAX_ERROR (MISSING_COMMA, FROM, PARENTHESES, RESERVED_KEYWORD, WHERE)",
        "UNKNOWN_TABLE",
        "UNKNOWN_COLUMN",
        "DATATYPE_MISMATCH",
        "DUPLICATE_ALIAS",
        "PERMISSION_DENIED",
        "SEMANTIC_ERROR (JOIN, GROUPBY, AGGREGATE, ALIAS, HAVING, ORDERBY, LIMIT, etc.)"
    ]
    
    print("\n" + "="*50)
    print("XAI ANALYSIS RESULTS")
    print("="*50)
    print(f"Predicted Class: {pred_class} - {error_categories[pred_class]}")
    print(f"Confidence Score: {probs[pred_class]*100:.2f}%")
    print("\nTop Contributing Tokens (Integrated Gradients):")
    
    # Sort tokens by absolute attribution score
    token_attrs = list(zip(tokens, attributions))
    token_attrs_sorted = sorted(token_attrs, key=lambda x: abs(x[1]), reverse=True)
    
    for t, attr in token_attrs_sorted[:10]:
        sign = "(+)" if attr >= 0 else "(-)"
        # Replace BPE space marker and replace any non-ascii characters to avoid Windows console errors
        t_clean = t.replace("Ġ", " ").encode('ascii', errors='replace').decode('ascii')
        print(f"  {t_clean:<15} | Attribution: {attr:+.6f} {sign}")
        
    print("\nExplanations figures saved successfully to:")
    print(f"  - {save_path / 'xai_attention_heatmap.png'}")
    print(f"  - {save_path / 'xai_token_importance.png'}")
    print("="*50)

if __name__ == "__main__":
    main()
