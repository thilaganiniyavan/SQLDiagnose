from typing import Dict, List

import pytest
from fastapi.testclient import TestClient

from models.domain.entities import ModelPrediction
from models.domain.interfaces import ISQLClassifier
from models.domain.labels import MODEL_CLASSES
from services.diagnosis import DiagnosisService
from .conftest import MUSIC


class FixedClassifier(ISQLClassifier):
    """Test double that always predicts the same class."""

    def __init__(self, cls: str, conf: float = 0.95):
        self.cls, self.conf = cls, conf

    def _pred(self) -> ModelPrediction:
        rest = (1 - self.conf) / (len(MODEL_CLASSES) - 1)
        return ModelPrediction(self.cls, self.conf, {c: (self.conf if c == self.cls else rest) for c in MODEL_CLASSES})

    def predict(self, query, schema=None):
        return self._pred()

    def predict_batch(self, queries, schemas) -> List[ModelPrediction]:
        return [self._pred() for _ in queries]

    def save_pretrained(self, directory, extra=None):
        pass

    def explain(self, query, schema=None, method="gxi"):
        return {"target_class": self.cls, "query_tokens": [{"token": "SELECT", "score": 1.0}], "schema_tokens": []}


def test_analyzer_verdict_wins_over_model(schema):
    svc = DiagnosisService(FixedClassifier("SEMANTIC_ERROR"))
    d = svc.diagnose("SELECT nme FROM singer", schema)
    assert d.error_class == "UNKNOWN_COLUMN" and d.decided_by == "analyzer" and d.notes


def test_agreement_is_reported(schema):
    d = DiagnosisService(FixedClassifier("UNKNOWN_COLUMN")).diagnose("SELECT nme FROM singer", schema)
    assert d.decided_by == "analyzer+model"


def test_clean_query_with_schema_stays_correct(schema):
    d = DiagnosisService(FixedClassifier("SYNTAX_ERROR", 0.99)).diagnose("SELECT name FROM singer", schema)
    assert d.error_class == "CORRECT" and any("suspects" in n for n in d.notes)


def test_model_decides_without_schema_when_confident():
    d = DiagnosisService(FixedClassifier("UNKNOWN_TABLE", 0.9)).diagnose("SELECT a FROM t")
    assert d.error_class == "UNKNOWN_TABLE" and d.decided_by == "model"
    d = DiagnosisService(FixedClassifier("UNKNOWN_TABLE", 0.5)).diagnose("SELECT a FROM t")
    assert d.error_class == "CORRECT"


def test_works_without_classifier(schema):
    d = DiagnosisService(None).diagnose("SELECT name FROM singer WHERE age = NULL", schema)
    assert d.error_class == "SEMANTIC_ERROR" and d.model is None


# ---------------------------------------------------------------------- API
@pytest.fixture(scope="module")
def client():
    from deployment.api.main import create_app, load_config
    cfg = load_config()
    cfg["api"]["load_generator_on_startup"] = False
    cfg["api"]["generator"] = ""
    app = create_app(cfg, load_models=False)
    with TestClient(app) as c:
        c.app.state.ctx.diagnosis.classifier = FixedClassifier("UNKNOWN_COLUMN")
        yield c


def test_health_and_labels(client):
    h = client.get("/api/v1/health").json()
    assert h["status"] == "ok" and h["model_loaded"] is True
    labels = client.get("/api/v1/labels").json()
    assert [l["name"] for l in labels][:2] == ["CORRECT", "SYNTAX_ERROR"] and len(labels) == 8


def test_diagnose_inline_schema(client):
    r = client.post("/api/v1/diagnose", json={"query": "SELECT nme FROM singer", "database_schema": MUSIC,
                                              "explain": True})
    body = r.json()
    assert r.status_code == 200
    assert body["error_class"] == "UNKNOWN_COLUMN" and body["decided_by"] == "analyzer+model"
    assert body["explanation"]["query_tokens"]


def test_predict_alias_and_policy(client):
    r = client.post("/api/v1/predict", json={"query": "SELECT * FROM stadium", "database_schema": MUSIC,
                                             "access_policy": {"restricted_tables": ["stadium"]}})
    assert r.json()["error_class"] == "PERMISSION_DENIED"


def test_repair_endpoint(client):
    body = client.post("/api/v1/repair", json={"query": "SELECT name FROM singr", "database_schema": MUSIC}).json()
    assert body["diagnosis"]["error_class"] == "UNKNOWN_TABLE"
    assert body["repair"]["success"] and body["repair"]["repaired_query"] == "SELECT name FROM singer"


def test_batch_and_upload(client):
    rows = client.post("/api/v1/batch", json={"queries": ["SELECT name FROM singer", "SELEC name FROM singer"],
                                              "database_schema": MUSIC, "repair": True}).json()
    assert [r["error_class"] for r in rows] == ["CORRECT", "SYNTAX_ERROR"]
    assert rows[1]["repair_success"] and rows[1]["repaired_query"] == "SELECT name FROM singer"
    csv = "query\nSELECT a FROM t WHERE b = NULL\n"
    up = client.post("/api/v1/upload", files={"file": ("q.csv", csv, "text/csv")}).json()
    assert up[0]["error_class"] == "SEMANTIC_ERROR"


def test_schema_endpoints(client):
    names = client.get("/api/v1/schemas").json()
    if names:
        info = client.get(f"/api/v1/schemas/{names[0]}").json()
        assert info["ddl"].startswith("CREATE TABLE")
    parsed = client.post("/api/v1/schemas/parse-ddl", json={"ddl": "CREATE TABLE t (id INT, v TEXT);"}).json()
    assert parsed["database_schema"]["t"]["columns"] == {"id": "INTEGER", "v": "TEXT"}
    bad = client.post("/api/v1/schemas/parse-sqlite", files={"file": ("x.sqlite", b"not a database", "application/octet-stream")})
    assert bad.status_code == 422


def test_validation_errors(client):
    assert client.post("/api/v1/diagnose", json={"query": ""}).status_code == 422
    assert client.post("/api/v1/diagnose", json={"query": "SELECT 1", "db_id": "does_not_exist"}).status_code == 404
    assert client.post("/api/v1/nl2sql", json={"question": "how many singers?"}).status_code == 422
    csv = "sql\nSELECT 1\n"
    assert client.post("/api/v1/upload", files={"file": ("q.csv", csv, "text/csv")}).status_code == 422


def test_metrics(client):
    m = client.get("/api/v1/metrics").json()
    assert m["diagnoses"] >= 1 and set(m["class_counts"]) >= {"CORRECT", "PERMISSION_DENIED"}
