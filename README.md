# NLP Research - SQL Error Classification

This directory contains research deliverables compiling state-of-the-art literature (2021-2026) regarding transformer models and SQL error detection.

## Contents
*   **[research_report.md](file:///C:/Users/tejes/Downloads/nlp/research_report.md)**: Full compilation of recent peer-reviewed paper summaries (Problem, Method, Dataset, Accuracy, Limitations), research gaps, and strategies for our project to outperform existing works.
*   **[datasets_review.md](file:///C:/Users/tejes/Downloads/nlp/datasets_review.md)**: Profile of publicly available SQL datasets (Spider, WikiSQL, BIRD, SParC, CoSQL, SQLShare, Kaggle, NL2SQL-BUGs) and recommendations for the best detection and classification combinations.
*   **[synthetic_pipeline_architecture.md](file:///C:/Users/tejes/Downloads/nlp/synthetic_pipeline_architecture.md)**: Architectural design for the automated generation of incorrect/buggy SQL statements from correct queries (covering 20+ syntactical and semantic mutations).
*   **[preprocessing_pipeline_design.md](file:///C:/Users/tejes/Downloads/nlp/preprocessing_pipeline_design.md)**: Conceptual design for query cleaning, semantic de-duplication, subword tokenization, sequence truncation, stratified splits, and HuggingFace compatibility.
*   **[model_comparison_report.md](file:///C:/Users/tejes/Downloads/nlp/model_comparison_report.md)**: Performance matrix and comparisons of BERT, RoBERTa, CodeBERT, GraphCodeBERT, PLBART, CodeT5, DistilBERT, and TinyBERT, plus recommendations.
*   **[training_pipeline_architecture.md](file:///C:/Users/tejes/Downloads/nlp/training_pipeline_architecture.md)**: Design for the fine-tuning framework featuring Group K-Fold splits, mixed-precision training, gradient accumulation, early stopping guards, validation evaluation, and system dashboard logging.
*   **[evaluation_methodology_design.md](file:///C:/Users/tejes/Downloads/nlp/evaluation_methodology_design.md)**: Design for evaluation protocols detailing classification metrics (Macro F1, Confusion Matrix, PR Curves), efficiency metrics (latency, memory footprint), statistical tests, and publication experiments.
*   **[software_architecture_design.md](file:///C:/Users/tejes/Downloads/nlp/software_architecture_design.md)**: Software architecture specifications outlining input schemas, data parsing layers, encoder pooling models, and predicted error category repair routers.
*   **[streamlit_dashboard_design.md](file:///C:/Users/tejes/Downloads/nlp/streamlit_dashboard_design.md)**: User interface layout wireframe, component configuration grids, status badges, and color themes for the dark-mode web application.
*   **[research_contributions.md](file:///C:/Users/tejes/Downloads/nlp/research_contributions.md)**: Proposed research contributions ranked by novelty (Multi-Class Taxonomy, AST Mutator Pipeline, XAI attention maps, and hybrid repair engines) suitable for ACL/EMNLP/KDD publication.
*   **[execution_roadmap.md](file:///C:/Users/tejes/Downloads/nlp/execution_roadmap.md)**: Execution milestones over a 5-week plan detailing tasks, deliverables, expected outputs, risks, and success criteria for paper draft and software prototype.











## Literature Scope
1.  **CodeBERT & GraphCodeBERT** (Structural and sequential code transformers)
2.  **PLBART & CodeT5** (Encoder-decoder code generators and validators)
3.  **VeriMinder** (Mitigating analytical vulnerabilities in natural language query structures)
4.  **SQL Injection Classifications** (e.g., synBERT models)
5.  **Confidence Estimation Systems** (AAAI 2025 selectively calibrated models)
