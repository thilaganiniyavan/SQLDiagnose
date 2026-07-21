# Intelligent SQL Error Detection & Multi-Class Classification

This repository hosts a research-grade, industry-standard project aimed at detecting and classifying SQL query errors into multiple semantic and structural categories. By moving beyond binary classification (correct vs. incorrect), this project enables precise error identification and diagnosis using Transformer models.

---

## Architecture Overview (Clean Architecture)

To maintain a decouplable, testable, and extendable pipeline, the project structure enforces **Clean Architecture** patterns:

```text
                               ┌─────────────────────────┐
                               │   Frameworks & Drivers  │
                               │ (FastAPI, Streamlit, Docker)
                               └────────────┬────────────┘
                                            │
                               ┌────────────▼────────────┐
                               │    Interface Adapters   │
                               │ (DataLoaders, PyTorch Model)
                               └────────────┬────────────┘
                                            │
                               ┌────────────▼────────────┐
                               │        Use Cases        │
                               │   (Train/Evaluate/Infer)│
                               └────────────┬────────────┘
                                            │
                               ┌────────────▼────────────┐
                               │       Core Domain       │
                               │ (SQLQuery, ModelInterface)
                               └─────────────────────────┘
```

- **Domain Layer (`models/domain/`)**: The core domain context. Contains data structures (`entities.py`) and generic class interfaces (`interfaces.py`). Free of external dependencies like PyTorch, HuggingFace, or FastAPI.
- **Use Case Layer (`training/`, `evaluation/`)**: Contains implementation of workflow processes (e.g. running optimizer step, validation loops, scheduling logs) using abstractions defined in the domain layer.
- **Interface Adapters (`datasets/`, `models/`)**: Translates datasets into model-friendly inputs, and wraps framework-specific implementations (e.g., PyTorch and HuggingFace models/tokenizers) to implement domain contracts.
- **Frameworks & Drivers (`deployment/`, `frontend/`, `configs/`)**: Concrete frameworks (Streamlit UI, FastAPI service, Docker virtualization, YAML file configs) powering the deployment.

---

## Directory Layout

```text
intelligent-sql-error-classifier/
├── configs/                  # Configuration files (YAML format)
│   ├── training_config.yaml  # Learning rates, optimizer details, seed, steps
│   ├── model_config.yaml     # Backbone models (e.g. RoBERTa), dropout, class mappings
│   ├── api_config.yaml       # API parameters (host, port, reload settings)
│   └── frontend_config.yaml  # Streamlit UI parameters (theme, endpoint urls)
├── datasets/                 # Pipeline for loading and normalizing dataset samples
│   ├── raw/                  # Placeholder for raw CSV/JSON SQL data files
│   ├── processed/            # Cached tokens and split preprocessed datasets
│   ├── data_processor.py     # SQL query casing, syntax cleaning and parsing helper
│   └── dataloader.py         # Custom PyTorch Dataset subclass & DataLoader builders
├── training/                 # Deep learning training workflow
│   ├── train.py              # Main training loop orchestrator
│   ├── losses.py             # Custom metrics (e.g., Focal Loss to counter class imbalance)
│   └── optimizer.py          # Weight decays, AdamW init, and scheduler setups
├── evaluation/               # Validation steps and diagnostic report generation
│   ├── evaluate.py           # Evaluation pipeline over held-out datasets
│   └── metrics.py            # Computes F1, precision, recall, confusion matrices
├── models/                   # Neural network layers and domain definitions
│   ├── domain/               # Domain core (Entities & Interfaces)
│   │   ├── entities.py       # SQLQuery & ClassificationResult dataclasses
│   │   └── interfaces.py     # Abstract base classes (ISQLModel, ISQLTokenizer)
│   ├── classifier.py         # Concrete Transformer adapter wrapping HuggingFace AutoModel
│   └── tokenizer.py          # Concrete Tokenizer adapter wrapping HuggingFace AutoTokenizer
├── deployment/               # REST API and Docker container configurations
│   ├── api/                  
│   │   ├── main.py           # FastAPI server lifecycle init and setup
│   │   ├── routes.py         # REST routing (/classify, /health)
│   │   └── schemas.py        # Pydantic request and response models
│   └── Dockerfile            # Multi-stage production container build script
├── frontend/                 # Interactive user dashboard
│   ├── app.py                # Streamlit visualization and text-editor entrypoint
│   └── components/           # UI elements and dynamic widgets
├── utils/                    # Common infrastructure utilities
│   ├── logger.py             # Structured logger config for execution tracking
│   └── helpers.py            # Reproducibility seed setup and directory handlers
├── logs/                     # Application and training run logs
├── experiments/              # Model weights, metrics, and checkpoints
└── reports/                  # Evaluation deliverables and figures
    ├── figures/              # Metrics visual plots (ROC curve, Confusion matrix)
    └── evaluation_report.md  # Detailed markdown summaries of experimental runs
```

---

## Getting Started

### Prerequisites
- Python 3.10+
- PyTorch 2.0+
- HuggingFace Transformers
- Docker (for deployment containerization)

### Step 1: Install Dependencies
Create a virtual environment and install core packages:
```bash
pip install torch transformers scikit-learn fastapi uvicorn streamlit pydantic pyyaml
```

### Step 2: Configure the Pipeline
Hyperparameters and models can be adjusted under `configs/model_config.yaml` and `configs/training_config.yaml`.

### Step 3: Run Training
Execute the training script:
```bash
python -m training.train
```

### Step 4: Run the API Server
Start the FastAPI server for serving model predictions:
```bash
uvicorn deployment.api.main:app --host 0.0.0.0 --port 8000
```

### Step 5: Start the Frontend UI
Launch Streamlit to inspect query errors manually:
```bash
streamlit run frontend/app.py
```
