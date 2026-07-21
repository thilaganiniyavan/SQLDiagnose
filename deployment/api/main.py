# main.py
# Clean Architecture: Frameworks & Drivers
# FastAPI Application Entrypoint

import yaml
import logging
import torch
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from models.classifier import TransformerSQLClassifier
from repair.repair_engine import SQLRepairEngine
from transformers import AutoTokenizer
from .routes import router

# Set up logging format
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s [%(name)s:%(filename)s:%(lineno)d] - %(message)s"
)
logger = logging.getLogger("api_server")

class SQLClassifierApp:
    """
    Manages API lifecycle events (e.g. model loading at startup) and mounts middlewares.
    """
    def __init__(self):
        self.app = FastAPI()
        self.config = self.load_config()
        self.initialize_app()

    def load_config(self) -> dict:
        """
        Loads the yaml api_config.yaml file from configs/.
        """
        project_root = Path(__file__).resolve().parents[2]
        config_path = project_root / "configs" / "api_config.yaml"
        
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        else:
            logger.warning(f"Configuration file not found at {config_path}. Using hardcoded API defaults.")
            return {
                "server": {"host": "0.0.0.0", "port": 8000},
                "app": {
                    "title": "SQL Error Classifier API",
                    "description": "SQL Error Classification REST endpoint.",
                    "version": "1.0.0",
                    "model_weights_path": "roberta-base",
                    "device": "cpu",
                    "enable_cors": True,
                    "allowed_origins": ["*"]
                }
            }

    def initialize_app(self):
        """
        Applies configuration settings, CORS mappings, and routers to the FastAPI app.
        """
        app_cfg = self.config.get("app", {})
        
        # Configure Swagger Metadata
        self.app.title = app_cfg.get("title", "SQL Error Classifier API")
        self.app.description = app_cfg.get("description", "")
        self.app.version = app_cfg.get("version", "1.0.0")
        
        # Configure CORS
        if app_cfg.get("enable_cors", True):
            self.app.add_middleware(
                CORSMiddleware,
                allow_origins=app_cfg.get("allowed_origins", ["*"]),
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )
            
        # Bind lifecycle events
        @self.app.on_event("startup")
        def startup_event():
            self.load_model_artifacts()
            
        # Register routes
        self.app.include_router(router)

    def load_model_artifacts(self):
        """
        Pre-loads the transformer checkpoints and tokenizer on startup.
        Uses a robust fallback to 'roberta-base' if custom checkpoint path doesn't exist.
        Supports loading custom PyTorch .pt checkpoints via state dictionary matching.
        """
        app_cfg = self.config.get("app", {})
        weights_path = app_cfg.get("model_weights_path", "experiments/checkpoints/best_model")
        device_target = app_cfg.get("device", "cpu")
        
        logger.info(f"Checking for model weights at target path: {weights_path}")
        
        # Resolve CUDA availability
        if device_target == "cuda" and not torch.cuda.is_available():
            logger.warning("CUDA target requested but GPU not available. Falling back to CPU execution.")
            device_target = "cpu"
            
        tokenizer = None
        classifier = None
        
        try:
            # Check if it is a PyTorch checkpoint (.pt) file
            if isinstance(weights_path, str) and weights_path.endswith(".pt") and Path(weights_path).exists():
                logger.info(f"Loading custom state dict checkpoint from: {weights_path}")
                base_model_name = "claudios/codebert-base"
                
                logger.info(f"Loading Tokenizer from: {base_model_name}")
                tokenizer = AutoTokenizer.from_pretrained(base_model_name)
                
                logger.info(f"Instantiating base model framework for sequence classification: {base_model_name}")
                classifier = TransformerSQLClassifier(model_name_or_path=base_model_name, num_labels=8)
                
                # Load state dict
                state = torch.load(weights_path, map_location="cpu")
                classifier.model.load_state_dict(state["model_state_dict"])
                classifier.model.to(device_target)
                logger.info(f"Custom model state dict successfully loaded on device: {device_target}")
                
            else:
                # Check if local path exists; if not, use roberta-base
                resolved_weights = weights_path
                if not Path(weights_path).exists() and weights_path != "roberta-base":
                    logger.warning(f"Fine-tuned model checkpoint directory '{weights_path}' was not found.")
                    logger.info("Falling back to pre-trained base model 'roberta-base' for API routing.")
                    resolved_weights = "roberta-base"
                    
                logger.info(f"Loading Tokenizer from: {resolved_weights}")
                tokenizer = AutoTokenizer.from_pretrained(resolved_weights)
                
                logger.info(f"Loading sequence classification model weights from: {resolved_weights}")
                classifier = TransformerSQLClassifier(model_name_or_path=resolved_weights, num_labels=8)
                classifier.model.to(device_target)
                logger.info(f"Model successfully loaded on device: {device_target}")
                
        except Exception as e:
            logger.error(f"Critical error loading model artifacts: {e}")
            # Robust fallback to base roberta-base model
            try:
                logger.info("Triggering absolute emergency fallback to base 'roberta-base'...")
                tokenizer = AutoTokenizer.from_pretrained("roberta-base")
                classifier = TransformerSQLClassifier(model_name_or_path="roberta-base", num_labels=8)
                classifier.model.to(device_target)
            except Exception as fallback_err:
                logger.critical(f"Emergency fallback failed: {fallback_err}")
                
        # Store state on app context
        self.app.state.classifier = classifier
        self.app.state.tokenizer = tokenizer
        self.app.state.repair_engine = SQLRepairEngine()
        
        # Initialize Metrics counters
        self.app.state.total_predictions = 0
        self.app.state.total_repairs = 0
        self.app.state.total_inference_time_ms = 0.0
        self.app.state.error_class_counts = {
            "CORRECT": 0,
            "SYNTAX_ERROR": 0,
            "UNKNOWN_TABLE": 0,
            "UNKNOWN_COLUMN": 0,
            "DATATYPE_MISMATCH": 0,
            "DUPLICATE_ALIAS": 0,
            "PERMISSION_DENIED": 0,
            "SEMANTIC_ERROR": 0
        }
        
        logger.info("FastAPI initialization of ML model state and repair engine is complete.")

# Expose app for uvicorn runner
app = SQLClassifierApp().app
