# main.py
# Clean Architecture: Frameworks & Drivers
# FastAPI application: configuration, model loading, shared state and the web app.
#
#   python -m uvicorn deployment.api.main:app --port 8000
#
# When the React app has been built (frontend/dist), it is served from the same origin: the UI at
# http://localhost:8000/, the REST API under /api/v1 and the interactive API docs at /docs.

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
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse

from models.domain.labels import CLASS_NAMES
from services.diagnosis import DiagnosisService
from services.jobs import JobQueue
from services.nl2sql import NL2SQLService
from services.schema_registry import SchemaRegistry
from services.workspace import WorkspaceStore
from .routes import router

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("sqldiagnose.api")
for _noisy in ("httpx", "httpcore", "huggingface_hub"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "configs" / "api_config.yaml"

# environment variable -> api config key
_ENV_OVERRIDES = {
    "SQLDIAGNOSE_MODEL_DIR": "model_dir",
    "SQLDIAGNOSE_DEVICE": "device",
    "SQLDIAGNOSE_GENERATOR": "generator",
    "SQLDIAGNOSE_WORKSPACE_DIR": "workspace_dir",
    "SQLDIAGNOSE_EXAMPLE_DB_DIR": "example_db_dir",
    "SQLDIAGNOSE_FRONTEND_DIST": "frontend_dist",
}


def load_config(path: Path = CONFIG_PATH) -> Dict[str, Any]:
    cfg = yaml.safe_load(path.read_text()) if path.exists() else {}
    api = cfg.setdefault("api", {})
    api.setdefault("device", "cpu")
    for env, key in _ENV_OVERRIDES.items():
        if env in os.environ:
            api[key] = os.environ[env]
    if "SQLDIAGNOSE_LIVE_SCHEMA" in os.environ:
        api["enable_live_schema_parsing"] = os.environ["SQLDIAGNOSE_LIVE_SCHEMA"].lower() in ("1", "true", "yes")
    return cfg


def _project_path(value: Optional[str]) -> Optional[Path]:
    if not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


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
        self.jobs = JobQueue(max_pending=int(api.get("max_pending_jobs", 20)))

        workspace_dir = _project_path(api.get("workspace_dir", "data/workspace"))
        self.workspace: Optional[WorkspaceStore] = WorkspaceStore(workspace_dir) if workspace_dir else None
        self.max_upload_mb = int(api.get("max_upload_mb", 100))
        self.example_db_dir = _project_path(api.get("example_db_dir", "data/raw/spider_data/database"))
        execution = api.get("execution", {}) or {}
        self.exec_timeout_s = float(execution.get("timeout_s", 5))
        self.exec_max_rows = int(execution.get("max_rows", 1000))
        self.reports_dir = _project_path(api.get("reports_dir", "reports"))

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

    def example_db_path(self, db_id: str) -> Optional[Path]:
        """Real SQLite file of a bundled example database, when it has been downloaded (make data)."""
        if not self.example_db_dir or self.registry.raw(db_id) is None:
            return None
        path = self.example_db_dir / db_id / f"{db_id}.sqlite"
        return path if path.is_file() else None

    def executable_db_ids(self):
        return [n for n in self.registry.names() if self.example_db_path(n) is not None]

    @property
    def generator_ready(self) -> bool:
        return self._nl2sql is not None

    def retry_generator(self):
        """Forget a previous load failure (e.g. no network) so the next request tries again."""
        with self._gen_lock:
            self.generator_error = None

    def nl2sql(self) -> Optional[NL2SQLService]:
        """Loads the generator on first use (it is large and not every deployment needs it)."""
        if self._nl2sql is not None or not self.generator_name:
            return self._nl2sql
        with self._gen_lock:
            if self._nl2sql is None and self.generator_error is None:
                try:
                    from models.generator import load_generator
                    self.generator = load_generator(self.generator_name, device=self.device)
                    self._nl2sql = NL2SQLService(self.generator, self.diagnosis)
                except Exception as e:                                    # network / disk errors
                    self.generator_error = str(e)
                    logger.error("Could not load generator %s: %s", self.generator_name, e)
        return self._nl2sql


# Content-Security-Policy for the web app (not for /docs, which loads Swagger UI from a CDN).
_APP_CSP = ("default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
            "font-src 'self' data:; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; "
            "base-uri 'self'; form-action 'self'")


def _mount_frontend(app: FastAPI, dist: Path):
    """Serves the built single-page app; unknown non-API paths fall back to index.html."""
    index = dist / "index.html"
    root = dist.resolve()

    def page(path: Path) -> FileResponse:
        hashed = path.parent.name == "assets"
        headers = {"Cache-Control": "public, max-age=31536000, immutable" if hashed else "no-cache"}
        if path.suffix == ".html":
            headers["Content-Security-Policy"] = _APP_CSP
        return FileResponse(path, headers=headers)

    @app.get("/", include_in_schema=False)
    def spa_root():
        return page(index)

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(404, "Not found")
        candidate = (dist / full_path).resolve()
        if candidate.is_file() and candidate.is_relative_to(root):
            return page(candidate)
        if "." in Path(full_path).name:           # a missing asset, not a client-side route
            raise HTTPException(404, "Not found")
        return page(index)


def create_app(cfg: Optional[Dict[str, Any]] = None, load_models: bool = True) -> FastAPI:
    cfg = cfg if cfg is not None else load_config()
    api = cfg.get("api", {})

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not hasattr(app.state, "ctx"):
            app.state.ctx = AppContext(cfg, load_models)
        yield
        if app.state.ctx.workspace:
            app.state.ctx.workspace.close()

    app = FastAPI(title=api.get("title", "SQLDiagnose API"), version=api.get("version", "2.0.0"),
                  description="Diagnose, explain and repair SQL queries; translate questions to verified SQL.",
                  lifespan=lifespan)
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(CORSMiddleware, allow_origins=api.get("cors_origins", ["*"]),
                       allow_methods=["*"], allow_headers=["*"])

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        return response

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse({"detail": "Internal server error. The details are in the server log."}, status_code=500)

    app.include_router(router, prefix="/api/v1")

    dist = _project_path(api.get("frontend_dist", "frontend/dist"))
    if dist and (dist / "index.html").is_file():
        _mount_frontend(app, dist)
    else:
        @app.get("/", include_in_schema=False)
        def root():
            return {"service": "SQLDiagnose", "docs": "/docs", "api": "/api/v1",
                    "ui": "not built - run `make frontend` (or `cd frontend && npm ci && npm run build`)"}

    return app


app = create_app()
