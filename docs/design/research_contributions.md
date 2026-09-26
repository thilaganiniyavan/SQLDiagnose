# Research Contributions & Novelty Ranking

This document outlines the core scientific and engineering contributions of this project that make it publishable in top-tier computer science venues (e.g., EMNLP, ACL, KDD, or ASE). The contributions are ranked from highest to lowest novelty.

---

## 1. Ranked Contributions by Novelty

### Contribution 1: Multi-Class SQL Diagnostic Error Taxonomy
*   **Novelty Rank**: **1 (Highest)**
*   **Description**: Establishing a structured, multi-class diagnostics taxonomy (8 standard classes) modeled after database execution engine compilers (e.g. distinguishing `TABLE_NOT_FOUND`, `DATA_TYPE_MISMATCH`, and `AMBIGUOUS_COLUMN`).
*   **Scientific Value**: Existing deep learning literature in SQL classification is overwhelmingly binary:
    - In security, models categorize queries as benign or SQL injection.
    - In translation (Text-to-SQL), models evaluate whether a query is correct or incorrect.
    By designing a multi-class diagnostics framework, we transform sequence classifiers into intelligent, explainable SQL compilers that can pinpoint specific compiler-level errors without executing queries, filling a significant research gap.

---

### Contribution 2: AST-Guided Synthetic SQL Mutation Pipeline
*   **Novelty Rank**: **2 (High)**
*   **Description**: Creating a data generation pipeline that translates correct query trees (Spider/BIRD) into incorrect statements by applying lexical, semantic, and schema-level mutations directly on Abstract Syntax Trees (ASTs), validated using a mock database parsing sandbox.
*   **Scientific Value**: Manual annotation of SQL errors is expensive. Simple string mutations (e.g. character deletes) yield unrealistic syntax structures. AST-level mutations mimic realistic human coding errors. Validating the generated queries in an execution sandbox guarantees that each mutated query is ground-truth buggy and correctly labeled, establishing a scalable paradigm for synthetic dataset generation.

---

### Contribution 3: Multi-Strategy Auto-Correction Suggestions Router
*   **Novelty Rank**: **3 (Medium-High)**
*   **Description**: Designing a hybrid repair suggestion engine that routes classified error states to specialized repair modules (Regex rules for syntax, Fuzzy matching for schema typos, and lightweight Seq2Seq generators for semantic logic errors).
*   **Scientific Value**: Existing Automated Program Repair (APR) systems typically rely entirely on heavy, slow LLMs to fix bugs. Our approach integrates classification class maps with cheap, targeted heuristic fixes. This reduces serving latency and computational costs, demonstrating a more practical architecture for production database gateways.

---

### Contribution 4: Explainable AI (XAI) via Token-to-Schema Attention Visualization
*   **Novelty Rank**: **4 (Medium)**
*   **Description**: Implementing self-attention heatmap visualization layers that trace attention weights between SQL query tokens and prepended database schema tokens (e.g., matching a table alias to its definition).
*   **Scientific Value**: Code models are frequently criticized for acting as "black boxes" that memorize string patterns. Visualizing token-to-schema attention maps proves that the transformer model detects semantic errors (like `COLUMN_NOT_FOUND`) by logically cross-referencing columns with table schemas, providing empirical evidence of structural code reasoning.

---

### Contribution 5: Cross-Dataset Generalization & Schema Robustness Testing
*   **Novelty Rank**: **5 (Medium)**
*   **Description**: Designing evaluation protocols to test model generalization against distribution shifts (e.g., training on modified Spider queries and validating on modified BIRD datasets) and database schema changes.
*   **Scientific Value**: Models often overfit to the schemas seen during training. Benchmarking performance across different datasets and splitting data by database groups tests model resilience against out-of-domain schemas, demonstrating true generalization.

---

### Contribution 6: Systematic Transformer Benchmarking & Ablation Study
*   **Novelty Rank**: **6 (Standard/Low)**
*   **Description**: Conducting a systematic evaluation of 8 transformer models (BERT, RoBERTa, CodeBERT, GraphCodeBERT, PLBART, CodeT5, DistilBERT, TinyBERT) across classification accuracy, VRAM, and latency, alongside ablation studies isolating the gains from Focal Loss and schema prefixing.
*   **Scientific Value**: While standard in literature, this benchmark is essential for documenting trade-offs (e.g., showing how CodeBERT balances accuracy and parameter efficiency) and justifying engineering design decisions.
