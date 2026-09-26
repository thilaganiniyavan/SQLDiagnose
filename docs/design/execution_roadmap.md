# Execution Roadmap: SQL Error Classification & Repair (5-Week Plan)

This document provides a complete weekly roadmap to complete both a research-grade paper and a working software prototype within five weeks.

---

## Weekly Milestones

### Week 1: Dataset Engineering & Synthetic Error Generation Pipeline
*   **Focus**: Mining correct query corpora and executing the AST mutation engine.
*   **Tasks**:
    1.  Extract correct base queries and database schema JSON files from the **Spider** and **BIRD** datasets.
    2.  Implement the Abstract Syntax Tree (AST) Parser and lexical, semantic, and schema-level SQL mutators in `datasets/data_processor.py`.
    3.  Create the query validation database sandbox to dry-run queries and label error outputs.
    4.  Run the pipeline to generate a balanced multi-class dataset of ~50,000 SQL statements.
*   **Deliverables**: A verified, labeled JSON/JSONL dataset.
*   **Expected Outputs**: `train.json` and `val.json` containing the fields: `original_query`, `modified_query`, `error_type`, `difficulty`, and `database_schema`.
*   **Risks**: Database verification dry-runs might have high latency.
    -   *Mitigation*: Implement multi-process pooling during the dry-run validation stage.
*   **Success Criteria**: Dataset generation completes with a 100% database verification rate and target error class representations above 5% each.

---

### Week 2: Preprocessing Pipeline & Baseline Model Fine-Tuning
*   **Focus**: Query tokenization, context building, and training the baseline classifiers.
*   **Tasks**:
    1.  Implement text cleaning (comment stripping), case normalization, and schema context prefixing.
    2.  Write the custom PyTorch dataset loader class (`SQLClassificationDataset`) in `datasets/dataloader.py`.
    3.  Configure Stratified Group K-Fold cross-validation by database schema ID.
    4.  Initialize logging integrations (TensorBoard and Weights & Biases).
    5.  Fine-tune baseline models (**DistilBERT** and **BERT**) on the classification task.
*   **Deliverables**: Active training pipeline and initial baseline metrics.
*   **Expected Outputs**: Code files in `datasets/` and initial weight checkpoints under `experiments/checkpoints/` for baselines.
*   **Risks**: Extreme class imbalance might prevent minority class convergence.
    -   *Mitigation*: Calculate and apply inverse-frequency class weights during baseline loss computation.
*   **Success Criteria**: Baseline models train successfully, achieving validation Macro F1 score $> 70\%$.

---

### Week 3: Primary Models Fine-Tuning, Custom Loss & Code Optimization
*   **Focus**: Fine-tuning primary models (CodeBERT and CodeT5) and implementing advanced training parameters.
*   **Tasks**:
    1.  Implement the custom **Focal Loss** function in `training/losses.py` to handle class imbalances.
    2.  Fine-tune the primary **CodeBERT** classification model using mixed-precision (FP16 AMP) and gradient accumulation.
    3.  Evaluate fine-tuning on **CodeT5** to serve as a secondary comparison architecture.
    4.  Implement the early stopping callback based on validation Macro F1 score metrics.
*   **Deliverables**: Optimally trained primary model checkpoints.
*   **Expected Outputs**: Fine-tuned weights for CodeBERT and comparative training reports.
*   **Risks**: Fine-tuning heavier models like CodeT5 might exceed GPU VRAM boundaries.
    -   *Mitigation*: Scale down physical batch sizes and scale up gradient accumulation steps to match target virtual batch size.
*   **Success Criteria**: CodeBERT model achieves validation Macro F1 score $> 90\%$.

---

### Week 4: Model Serving (FastAPI), Suggested Fix Engine & UI Dashboard
*   **Focus**: Packaging the model for inference, implementing the repair router, and building the dashboard.
*   **Tasks**:
    1.  Deploy the model weights inside a FastAPI REST server with health checks and endpoints (`POST /classify`).
    2.  Implement the **Suggested Fix Engine** routing error classes to:
        -   *Regex Templates*: For lexical syntax errors.
        -   *Fuzzy Schema Matchers*: For table/column spelling mismatches.
        -   *CodeT5 Generative Decoder*: For complex semantic repair.
    3.  Build the Streamlit web dashboard (`frontend/app.py`) incorporating editor panels, probability charts, and attention heatmaps.
    4.  Configure the Docker container (`deployment/Dockerfile`) mounting backend services.
*   **Deliverables**: Containerized model serving system and a functioning web dashboard.
*   **Expected Outputs**: Docker images, running container service, and dashboard UI interfaces.
*   **Risks**: Generative repair decoders might yield syntactically invalid SQL strings.
    -   *Mitigation*: Pass generated repairs through the database sandbox validation layer before presenting them as suggestions.
*   **Success Criteria**: End-to-end local latency (from query post to UI display of prediction and repair suggestion) remains under $100$ ms.

---

### Week 5: Robustness Testing, Significance Audits & Paper Writing
*   **Focus**: Performance evaluation, statistical analysis, and compiling the publication draft.
*   **Tasks**:
    1.  Execute cross-dataset generalization testing (evaluating Spider-trained models on BIRD test sets).
    2.  Perform the ablation studies (comparing model performance with/without schema context and Focal Loss).
    3.  Conduct **McNemar's** and **Wilcoxon signed-rank** statistical significance tests.
    4.  Draw the latency-versus-accuracy Pareto curves for all 8 architectures.
    5.  Draft the publication-ready paper: Abstract, Introduction, System Design, Experiments, Results, and Future Work.
*   **Deliverables**: Camera-ready research paper draft and final codebase walkthrough.
*   **Expected Outputs**: PDF document draft (`SQL_Classification_Paper.pdf`) and evaluation visualization charts.
*   **Risks**: Performance drop on cross-dataset evaluation could highlight generalization issues.
    -   *Mitigation*: Perform schema normalization during preprocessing to decouple SQL grammar from specific database terms.
*   **Success Criteria**: The paper draft is completed, proving that the proposed system outperforms standard baselines with statistical significance ($p < 0.05$).
