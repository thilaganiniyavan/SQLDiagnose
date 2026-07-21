# Model Comparison Report: SQL Error Classification

This report compares eight transformer architectures for the task of multi-class SQL error classification. It analyzes their parameter counts, relative accuracies, training times, memory footprints, inference speeds, and project suitability, concluding with concrete model recommendations.

---

## 1. Model Comparison Matrix

The table below outlines typical characteristics of each model when fine-tuned on code classification datasets:

| Model | Parameter Count | Relative Accuracy | Training Time | Memory Footprint (VRAM) | Inference Speed (CPU) | SQL Suitability |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **BERT** (`bert-base-uncased`) | ~110M | Moderate | Baseline | Moderate (~12 GB) | Fast (~15 ms) | **Low-to-Moderate**: Lacks vocabulary/pretraining for coding languages. |
| **RoBERTa** (`roberta-base`) | ~125M | Moderate-High | Baseline | Moderate (~12 GB) | Fast (~15 ms) | **Moderate**: Better optimized than BERT, but still trained on general text. |
| **CodeBERT** (`codebert-base`) | ~125M | High | Baseline | Moderate (~12 GB) | Fast (~15 ms) | **Very High**: Pretrained on code text; natural encoder-only classifier. |
| **GraphCodeBERT** | ~125M | Very High | High | High (~16 GB) | Slow (~45 ms) | **High**: Excellent structure tracking, but parsing AST/Data Flow is slow. |
| **PLBART** (`plbart-base`) | ~140M | High | High | High (~16 GB) | Moderate (~25 ms) | **Moderate**: Designed for generative Seq2Seq tasks rather than classification. |
| **CodeT5** (`codet5-base`) | ~220M | Outstanding | High | High (~20 GB) | Moderate-Slow (~30 ms)| **Very High**: Identifier-aware; excellent logic capture but heavy structure. |
| **DistilBERT** | ~66M | Moderate | Low (50% faster) | Low (~6 GB) | Very Fast (~6 ms) | **Moderate**: Standard lightweight baseline; lacks code pretraining. |
| **TinyBERT** | ~14.5M | Low-Moderate | Very Low | Ultra-Low (<2 GB) | Ultra-Fast (~2 ms) | **Low**: Best for micro-edge/browser constraints, lacks semantic depth. |

*Note: Inference speed and VRAM estimates are based on a batch size of 16 and a maximum sequence length of 256.*

---

## 2. Core Comparison Insights

### A. General Text vs. Code Pre-trained Models
*   **BERT / RoBERTa / DistilBERT**: Pre-trained on Wikipedia and BookCorpus. They lack vocabulary tokens specific to database syntax (e.g. relational joins, database operators) and split them into multiple subword fragments. This increases query sequence lengths and leads to poor syntactic representation.
*   **CodeBERT / CodeT5 / PLBART**: Pre-trained on programming languages. Their tokenizers preserve structural keywords (e.g., `SELECT`, `GROUP BY`, `IS NULL`) and database identifiers, yielding much better syntax and semantic understanding.

### B. Encoder-Only vs. Encoder-Decoder Architectures
*   **Encoder-Only (CodeBERT, BERT, RoBERTa, DistilBERT)**: Process sequences bidirectionally and map them to a single classification token (`[CLS]` or `<s>`). They are computationally efficient and naturally suited for classification heads.
*   **Encoder-Decoder (CodeT5, PLBART)**: Designed for text generation (e.g. generating SQL from NL). While highly accurate, they carry redundant parameters in the decoder stack during classification tasks, leading to slower inference and higher memory utilization.

### C. Structural Additions (GraphCodeBERT)
*   **GraphCodeBERT** incorporates data-flow graphs. While it provides outstanding accuracy for tracking variables in source files (e.g., vulnerability tracking), generating AST and data-flow trees on the fly creates high data-preprocessing latency, making it less suitable for high-throughput REST APIs.

---

## 3. Recommended Architectures

### Primary Recommendation: CodeBERT (`microsoft/codebert-base`)
*   **Why**: 
    1.  **Ideal for Classification**: As an encoder-only model, it passes sequences directly to a dense classifier layer, avoiding the decoder overhead of CodeT5.
    2.  **Code-Aware Embeddings**: Pre-trained on bimodal data (Natural Language and Code), it inherently understands relational syntax, token dependencies, and schema mappings.
    3.  **Efficiency**: It has only 125M parameters, making it highly competitive in accuracy while requiring significantly less VRAM and serving with lower latency than CodeT5.

### Lightweight Baseline Recommendation: DistilBERT (`distilbert-base-uncased`)
*   **Why**:
    1.  **High Throughput / Low Latency**: With only 66M parameters, DistilBERT is nearly twice as fast during inference and requires half the VRAM of standard BERT/CodeBERT.
    2.  **Resource Constraints**: DistilBERT can be easily served on cheap, single-core CPU instances without bottlenecking our FastAPI deployment gateway.
    3.  **Benchmark Standard**: Serves as a perfect baseline to measure the performance improvement gained by migrating to code-specific pre-trained models.
