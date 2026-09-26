# Preprocessing Pipeline Design

This document details the architectural design and operations of the preprocessing pipeline for the multi-class SQL error classifier. The pipeline processes raw query datasets (such as Spider, BIRD, or our synthetic mutator output) and formats them into clean, balanced tensors compatible with HuggingFace Datasets and PyTorch models.

---

## 1. Pipeline Data Flow

```mermaid
flowchart TD
    Raw[Raw SQL Data + Schemas] --> Clean[1. Cleaning & Comment Stripper]
    Clean --> Dedup[2. Deduplication & Semantic Leakage Filter]
    Dedup --> Normal[3. SQL Token Normalization]
    Normal --> Augment[4. Minority Class Augmentation]
    Augment --> Split[5. Stratified & Database-Level Split]
    
    subgraph Tokenizer Engine (HuggingFace)
        Split --> Tokenize[6. Subword Tokenization]
        Tokenize --> LengthLimit[7. Sequence Chunking & Truncation]
        LengthLimit --> Vocab[8. Vocab Mapping & Special Token Injection]
    end

    LengthLimit --> LabelEnc[9. Label & Class Balance Encoding]
    LabelEnc --> HFDataset[10. HuggingFace Dataset Generation]
```

---

## 2. Preprocessing Stages Detailed

### Stage 1: Cleaning
-   **Operation**: Removes execution-irrelevant tokens to minimize sequence noise.
-   **Details**:
    -   Strips single-line SQL comments starting with `--`.
    -   Strips block comments enclosed in `/* ... */`.
    -   Normalizes multiple spaces, tabs, and newline characters (`\n`, `\r`) into single spacing.
    -   Removes database execution engine specific prefixes (e.g., `explain query plan` or engine transaction declarations).

### Stage 2: Deduplication & Semantic Leakage Filter
-   **Operation**: Filters duplicate entries to prevent over-optimistic evaluation metrics.
-   **Details**:
    -   **Exact Duplicates**: Deletes identical query strings.
    -   **Semantic Leakage Filtering**: Normalizes table/column aliases to standard variables (e.g. `SELECT alias1.col FROM table AS alias1` becomes `SELECT a.c FROM t AS a`). Queries that become identical after alias normalization are discarded from different train/test splits to ensure model validates on true syntax logic variation.

### Stage 3: Normalization
-   **Operation**: Enhances semantic consistency across dialects.
-   **Details**:
    -   **Keyword Casing**: Standardizes all SQL reserved words (e.g. `select`, `join`, `where`, `group by`) to uppercase, or lowercase consistently based on configuration settings.
    -   **Schema Prefixing (Optional)**: If schema-aware validation is enabled, serializes the catalog structures into a standardized lookup string prepended to the SQL query.
        -   *Format*: `[SCHEMA] table1(col1 INT, col2 VARCHAR) [QUERY] SELECT col1 FROM table1`

### Stage 4: Data Augmentation
-   **Operation**: Artificially expands the volume and diversity of minority classes to counter class imbalance.
-   **Details**:
    -   **Alias Permutation**: Swaps table alias names (e.g., renaming alias `u` to `users_list` or `u1`).
    -   **Keyword Perturbation**: Randomizes lowercase/uppercase of keywords to ensure the transformer model does not latch onto case variations as indicators of errors.
    -   **Value Mutation**: Mutates literal values inside filters (e.g. changing `WHERE age > 18` to `WHERE age > 25`) to increase dataset variations without changing logic boundaries.

### Stage 5: Train / Validation / Test Split
-   **Operation**: Evaluates cross-schema generalization capabilities.
-   **Details**:
    -   **Database-Level Split**: Following Yale's Spider benchmark, we partition the dataset by **Database Schema ID** rather than random query-level indexing. This ensures that the validation and test datasets contain databases and schemas that the model has never encountered during training.
    -   **Stratification**: For the remaining classes, it splits queries to maintain a consistent proportion of error category labels across training and testing partitions.

### Stage 6: Tokenization
-   **Operation**: Converts raw strings into token subword indices.
-   **Details**:
    -   Utilizes the pre-trained tokenizer matching the backbone transformer (e.g., `RobertaTokenizerFast` or `T5TokenizerFast`).
    -   Tokenizes subwords using Byte-Pair Encoding (BPE) or WordPiece, ensuring database identifier prefixes (like snake_case `user_id` or camelCase `userId`) are split into subword fragments rather than treated as Out-of-Vocabulary (OOV) tokens.

### Stage 7: Handling Long SQL Queries
-   **Operation**: Manages query sequence variations to comply with context window constraints.
-   **Details**:
    -   **Safe Truncation**: Truncates queries at `max_sequence_length` (e.g., 256 or 512 tokens).
    -   **Truncation Exclusion**: If a query is truncated, syntactic integrity is lost. This can cause a correct query to be misidentified as a syntax error. To prevent this, the pipeline:
        1.  Discards truncated correct queries from validation/test evaluation to avoid false label matching.
        2.  Or implements a sliding window with overlap to capture long queries across multiple input spans.

### Stage 8: Vocabulary Management
-   **Operation**: Enforces syntax tokens.
-   **Details**:
    -   Loads vocabulary indices directly from the HuggingFace tokenizer.
    -   Registers custom tokens if necessary (e.g., schema boundaries `[SCHEMA]`, `[QUERY]` or sql components like `!=`) so they are not split into subwords, allowing the attention heads to register them as distinct keywords.

### Stage 9: Label Encoding & Class Balancing
-   **Operation**: Converts target error classes into standard integer classifications and adjusts weights.
-   **Details**:
    -   **Label Encoding**: Encodes text class IDs (`SYNTAX_ERROR` $\to$ `1`, `TABLE_NOT_FOUND` $\to$ `2`, etc.) to numerical values.
    -   **Class Weight Computation**: Calculates inverse frequency class weights to scale loss gradients:
        $$W_c = \frac{N_{\text{total}}}{C \times N_c}$$
        where $C$ is the number of classes, $N_c$ is the sample count for class $c$, and $N_{\text{total}}$ is the total dataset volume.

### Stage 10: HuggingFace Dataset Generation
-   **Operation**: Packages datasets into clean memory-mapped HuggingFace files.
-   **Details**:
    -   Loads preprocessed features into a HuggingFace `Dataset` dictionary containing keys:
        -   `input_ids`: Tensor mapping of vocabulary tokens.
        -   `attention_mask`: Attention markers masking out padding positions.
        -   `labels`: Integer encoding of the target SQL error class.
    -   Enables caching and lazy disk loading using Apache Arrow format, ensuring training remains memory-efficient.
