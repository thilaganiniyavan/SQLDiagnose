# main.py
# Clean Architecture: Frameworks & Drivers
# FastAPI application: configuration, model loading and shared state.
#
#   python -m uvicorn deployment.api.main:app --port 8000

import json
import logging
import os
import threading
import time
from collections import Counter
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from models.domain.labels import CLASS_NAMES
from services.diagnosis import DiagnosisService
from services.nl2sql import NL2SQLService
from services.schema_registry import SchemaRegistry
from .routes import router

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("sqldiagnose.api")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "configs" / "api_config.yaml"


def load_config(path: Path = CONFIG_PATH) -> Dict[str, Any]:
    cfg = yaml.safe_load(path.read_text()) if path.exists() else {}
    api = cfg.setdefault("api", {})
    api["model_dir"] = os.environ.get("SQLDIAGNOSE_MODEL_DIR", api.get("model_dir", ""))
    api["device"] = os.environ.get("SQLDIAGNOSE_DEVICE", api.get("device", "cpu"))
    api["generator"] = os.environ.get("SQLDIAGNOSE_GENERATOR", api.get("generator", ""))
    return cfg


class Metrics:
    def __init__(self):
        self._lock = threading.Lock()
        self.started = time.time()
        self.requests: Counter = Counter()
        self.classes: Counter = Counter({c: 0 for c in CLASS_NAMES})
        self.diagnoses = 0
        self.latency_total = 0.0
        self.repairs = 0
        self.repairs_ok = 0

    def count(self, endpoint: str):
        with self._lock:
            self.requests[endpoint] += 1

    def record_diagnosis(self, cls: str, latency_ms: float):
        with self._lock:
            self.diagnoses += 1
            self.latency_total += latency_ms
            self.classes[cls] += 1

    def record_repair(self, success: bool):
        with self._lock:
            self.repairs += 1
            self.repairs_ok += int(success)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {"uptime_s": round(time.time() - self.started, 1), "requests": dict(self.requests),
                    "diagnoses": self.diagnoses, "repairs": self.repairs, "repairs_successful": self.repairs_ok,
                    "mean_diagnosis_latency_ms": round(self.latency_total / self.diagnoses, 2) if self.diagnoses else 0.0,
                    "class_counts": dict(self.classes)}


class AppContext:
    """Everything the route handlers share. Built once at startup."""

    def __init__(self, cfg: Dict[str, Any], load_models: bool = True):
        api = cfg.get("api", {})
        self.version = api.get("version", "2.0.0")
        self.device = api.get("device", "cpu")
        self.max_batch = int(api.get("max_batch", 500))
        self.enable_live_schema = bool(api.get("enable_live_schema_parsing", False))
        self.generator_name = api.get("generator") or None
        self.registry = SchemaRegistry()
        self.metrics = Metrics()
        self.model_info: Optional[Dict[str, Any]] = None
        self.generator = None
        self.generator_error: Optional[str] = None
        self._gen_lock = threading.Lock()
        self._nl2sql: Optional[NL2SQLService] = None

        classifier = None
        model_dir = api.get("model_dir")
        if load_models and model_dir:
            path = Path(model_dir)
            path = path if path.is_absolute() else PROJECT_ROOT / path
            if (path / "sqldiagnose_labels.json").exists():
                if self.device == "cuda":
                    import torch
                    if not torch.cuda.is_available():
                        logger.warning("CUDA requested but unavailable; using CPU.")
                        self.device = "cpu"
                from models.classifier import SQLErrorClassifier
                classifier = SQLErrorClassifier.from_pretrained(str(path), device=self.device)
                meta = json.loads((path / "sqldiagnose_labels.json").read_text())
                self.model_info = {"path": str(path.relative_to(PROJECT_ROOT) if path.is_relative_to(PROJECT_ROOT) else path),
                                   "backbone": meta.get("backbone"), "labels": classifier.labels,
                                   "validation": meta.get("validation"), "parameters": classifier.num_parameters()}
                logger.info("Classifier loaded from %s", path)
            else:
                logger.warning("No classifier checkpoint at %s - running with the deterministic analyzer only. "
                               "Train one with `python -m training.train`.", path)
        self.diagnosis = DiagnosisService(classifier, model_threshold=float(api.get("model_threshold", 0.8)))
        if load_models and api.get("load_generator_on_startup"):
            self.nl2sql()

    def nl2sql(self) -> Optional[NL2SQLService]:
        """Loads the generator on first use (it is large and not every deployment needs it)."""
        if self._nl2sql is not None or not self.generator_name:
            return self._nl2sql
        with self._gen_lock:
            if self._nl2sql is None and self.generator_error is None:
                try:
                    from models.generator import T5SQLGenerator
                    self.generator = T5SQLGenerator(self.generator_name, device=self.device)
                    self._nl2sql = NL2SQLService(self.generator, self.diagnosis)
                except Exception as e:                                    # network / disk errors
                    self.generator_error = str(e)
                    logger.error("Could not load generator %s: %s", self.generator_name, e)
        return self._nl2sql


def create_app(cfg: Optional[Dict[str, Any]] = None, load_models: bool = True) -> FastAPI:
    cfg = cfg if cfg is not None else load_config()
    api = cfg.get("api", {})

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not hasattr(app.state, "ctx"):
            app.state.ctx = AppContext(cfg, load_models)
        yield

    app = FastAPI(title=api.get("title", "SQLDiagnose API"), version=api.get("version", "2.0.0"),
                  description="Diagnose, explain and repair SQL queries; translate questions to verified SQL.",
                  lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=api.get("cors_origins", ["*"]),
                       allow_methods=["*"], allow_headers=["*"])
    app.include_router(router, prefix="/api/v1")

    @app.get("/", include_in_schema=False)
    def root():
        return {"service": "SQLDiagnose", "docs": "/docs", "api": "/api/v1"}

    return app


app = create_app()
