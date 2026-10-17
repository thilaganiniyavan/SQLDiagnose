"""Endpoints used by the web app: analyze, execution, workspace (saved schemas, history), NL2SQL jobs,
research results and serving the built single-page app."""

import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from services.executor import ExecutionError, execute_readonly
from services.jobs import JobQueue, QueueFull
from .conftest import MUSIC
from .test_nl2sql import ScriptedGenerator

CLIENT = {"X-Client-Id": "test-client-0001"}
OTHER = {"X-Client-Id": "test-client-0002"}


def _make_db(path):
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE singer (singer_id INTEGER PRIMARY KEY, name TEXT, country TEXT, age INTEGER);
        INSERT INTO singer VALUES (1, 'Joe', 'France', 52), (2, 'Ann', 'Spain', 29), (3, 'Li', 'France', 41);
    """)
    conn.commit()
    conn.close()
    return path


@pytest.fixture()
def app_env(tmp_path):
    from deployment.api.main import create_app, load_config
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>SQLDiagnose</title><div id=root></div>")
    (dist / "assets" / "app-1234.js").write_text("console.log('app')")
    examples = tmp_path / "examples"
    (examples / "concert_singer").mkdir(parents=True)
    _make_db(examples / "concert_singer" / "concert_singer.sqlite")

    cfg = load_config()
    api = cfg["api"]
    api.update(generator="", load_generator_on_startup=False, workspace_dir=str(tmp_path / "ws"),
               frontend_dist=str(dist), example_db_dir=str(examples))
    app = create_app(cfg, load_models=False)
    with TestClient(app) as c:
        yield c, tmp_path


@pytest.fixture()
def client(app_env):
    return app_env[0]


# ---------------------------------------------------------------------- analyze
def test_analyze_diagnoses_repairs_and_records_history(client):
    r = client.post("/api/v1/analyze", headers=CLIENT,
                    json={"query": "SELECT name FROM singr", "database_schema": MUSIC})
    body = r.json()
    assert r.status_code == 200
    assert body["diagnosis"]["error_class"] == "UNKNOWN_TABLE"
    assert body["repair"]["success"] and body["repair"]["repaired_query"] == "SELECT name FROM singer"
    assert body["history_id"]

    hist = client.get("/api/v1/workspace/history", headers=CLIENT).json()
    assert hist["total"] == 1 and hist["items"][0]["error_class"] == "UNKNOWN_TABLE"
    item = client.get(f"/api/v1/workspace/history/{body['history_id']}", headers=CLIENT).json()
    assert item["result"]["repair"]["repaired_query"] == "SELECT name FROM singer"
    assert item["context"] == {"database_schema": MUSIC}
    # other browsers do not see it
    assert client.get("/api/v1/workspace/history", headers=OTHER).json()["total"] == 0


def test_analyze_correct_query_has_no_repair_and_no_history_without_client(client):
    body = client.post("/api/v1/analyze", json={"query": "SELECT name FROM singer", "db_id": "concert_singer"}).json()
    assert body["diagnosis"]["error_class"] == "CORRECT" and body["repair"] is None
    assert body["history_id"] is None


def test_invalid_client_id_is_rejected(client):
    r = client.post("/api/v1/analyze", headers={"X-Client-Id": "bad id!"}, json={"query": "SELECT 1"})
    assert r.status_code == 400


def test_history_filter_search_delete_and_clear(client):
    for q in ("SELECT name FROM singr", "SELECT nme FROM singer", "SELECT name FROM singer"):
        client.post("/api/v1/analyze", headers=CLIENT, json={"query": q, "database_schema": MUSIC})
    assert client.get("/api/v1/workspace/history?search=nme", headers=CLIENT).json()["total"] == 1
    assert client.get("/api/v1/workspace/history?search=UNKNOWN_TABLE", headers=CLIENT).json()["total"] == 1
    assert client.get("/api/v1/workspace/history?search=100%25", headers=CLIENT).json()["total"] == 0
    assert client.get("/api/v1/workspace/history?kind=nl2sql", headers=CLIENT).json()["total"] == 0
    items = client.get("/api/v1/workspace/history?limit=2", headers=CLIENT).json()
    assert items["total"] == 3 and len(items["items"]) == 2
    assert items["items"][0]["title"] == "SELECT name FROM singer"          # newest first
    assert client.delete(f"/api/v1/workspace/history/{items['items'][0]['id']}", headers=CLIENT).status_code == 204
    assert client.delete(f"/api/v1/workspace/history/{items['items'][0]['id']}", headers=CLIENT).status_code == 404
    assert client.delete("/api/v1/workspace/history", headers=CLIENT).json() == {"deleted": 2}


def test_upload_applies_access_policy(client):
    csv = "query\nSELECT Name FROM stadium\nSELECT Name FROM singer\n"
    rows = client.post("/api/v1/upload?db_id=concert_singer&repair=false",
                       data={"access_policy": '{"restricted_tables": ["stadium"]}'},
                       files={"file": ("q.csv", csv, "text/csv")}).json()
    assert [r["error_class"] for r in rows] == ["PERMISSION_DENIED", "CORRECT"]
    bad = client.post("/api/v1/upload", data={"access_policy": "{"}, files={"file": ("q.csv", csv, "text/csv")})
    assert bad.status_code == 422


def test_batch_is_recorded(client):
    rows = client.post("/api/v1/batch", headers=CLIENT, json={
        "queries": ["SELECT name FROM singer", "SELEC name FROM singer"], "database_schema": MUSIC, "repair": True}).json()
    assert len(rows) == 2
    item = client.get("/api/v1/workspace/history?kind=batch", headers=CLIENT).json()["items"][0]
    assert item["summary"] == {"total": 2, "errors": 1, "repaired": 1}


# ---------------------------------------------------------------------- saved schemas
def test_saved_schema_lifecycle(client):
    r = client.post("/api/v1/workspace/schemas", headers=CLIENT,
                    json={"name": "music", "source": "json", "database_schema": MUSIC,
                          "access_policy": {"restricted_tables": ["stadium"]}})
    assert r.status_code == 201
    saved = r.json()
    assert saved["tables"] == 4 and saved["executable"] is False
    sid = saved["id"]
    assert [s["name"] for s in client.get("/api/v1/workspace/schemas", headers=CLIENT).json()] == ["music"]
    assert client.get("/api/v1/workspace/schemas", headers=OTHER).json() == []
    assert client.get(f"/api/v1/workspace/schemas/{sid}", headers=OTHER).status_code == 404

    # diagnose by schema id: the saved access policy applies
    d = client.post("/api/v1/diagnose", headers=CLIENT, json={"query": "SELECT name FROM stadium", "schema_id": sid}).json()
    assert d["error_class"] == "PERMISSION_DENIED"
    d = client.post("/api/v1/diagnose", headers=CLIENT, json={"query": "SELECT nme FROM singer", "schema_id": sid}).json()
    assert d["error_class"] == "UNKNOWN_COLUMN"

    up = client.patch(f"/api/v1/workspace/schemas/{sid}", headers=CLIENT,
                      json={"name": "music v2", "clear_access_policy": True}).json()
    assert up["name"] == "music v2" and up["access_policy"] is None
    detail = client.get(f"/api/v1/workspace/schemas/{sid}", headers=CLIENT).json()
    assert detail["ddl"].startswith("CREATE TABLE")
    d = client.post("/api/v1/diagnose", headers=CLIENT, json={"query": "SELECT name FROM stadium", "schema_id": sid}).json()
    assert d["error_class"] == "CORRECT"

    assert client.delete(f"/api/v1/workspace/schemas/{sid}", headers=CLIENT).status_code == 204
    assert client.post("/api/v1/diagnose", headers=CLIENT, json={"query": "SELECT 1", "schema_id": sid}).status_code == 404


def test_saved_schema_validation(client):
    assert client.post("/api/v1/workspace/schemas", headers=CLIENT,
                       json={"name": "x", "database_schema": {}}).status_code == 422
    assert client.post("/api/v1/workspace/schemas", headers=CLIENT,
                       json={"name": "x", "database_schema": {"t": {"columns": 5}}}).status_code == 422


def test_sqlite_upload_is_kept_and_executable(client, tmp_path):
    data = _make_db(tmp_path / "shop.sqlite").read_bytes()
    r = client.post("/api/v1/workspace/schemas/sqlite", headers=CLIENT,
                    files={"file": ("shop.sqlite", data, "application/octet-stream")})
    assert r.status_code == 201
    saved = r.json()
    assert saved["name"] == "shop" and saved["executable"] and saved["source"] == "sqlite"
    res = client.post("/api/v1/execute", headers=CLIENT,
                      json={"query": "SELECT name FROM singer WHERE country = 'France' ORDER BY age", "schema_id": saved["id"]}).json()
    assert res["columns"] == ["name"] and res["rows"] == [["Li"], ["Joe"]]
    # without keeping the file the schema is still saved, but cannot be executed
    r = client.post("/api/v1/workspace/schemas/sqlite", headers=CLIENT, data={"keep_database": "false", "name": "copy"},
                    files={"file": ("shop.sqlite", data, "application/octet-stream")}).json()
    assert r["name"] == "copy" and not r["executable"]
    assert client.post("/api/v1/execute", headers=CLIENT, json={"query": "SELECT 1", "schema_id": r["id"]}).status_code == 409
    bad = client.post("/api/v1/workspace/schemas/sqlite", headers=CLIENT, files={"file": ("x.db", b"nope", "application/octet-stream")})
    assert bad.status_code == 422


# ---------------------------------------------------------------------- execution
def test_execute_example_database(client):
    res = client.post("/api/v1/execute", json={"query": "SELECT count(*) AS n FROM singer;", "db_id": "concert_singer"}).json()
    assert res == {**res, "columns": ["n"], "rows": [[3]], "truncated": False}
    res = client.post("/api/v1/execute", json={"query": "SELECT * FROM singer", "db_id": "concert_singer", "max_rows": 2}).json()
    assert res["row_count"] == 2 and res["truncated"]
    dbs = {d["db_id"]: d for d in client.get("/api/v1/databases").json()}
    assert dbs["concert_singer"]["executable"] and dbs["concert_singer"]["tables"] > 0
    assert client.get("/api/v1/schemas/concert_singer").json()["executable"] is True
    assert client.get("/api/v1/health").json()["executable_databases"] == 1


@pytest.mark.parametrize("query,message", [
    ("DELETE FROM singer", "read-only"),
    ("UPDATE singer SET age = 1", "read-only"),
    ("PRAGMA table_info(singer)", "read-only"),
    ("SELECT 1; SELECT 2", "one statement"),
    ("SELECT nme FROM singer", "no such column"),
])
def test_execute_rejects_non_select_and_errors(client, query, message):
    r = client.post("/api/v1/execute", json={"query": query, "db_id": "concert_singer"})
    assert r.status_code == 422 and message in r.json()["detail"]


def test_execute_needs_data(client):
    assert client.post("/api/v1/execute", json={"query": "SELECT 1"}).status_code == 422
    assert client.post("/api/v1/execute", json={"query": "SELECT 1", "db_id": "nope"}).status_code == 404
    other = next(n for n in client.get("/api/v1/schemas").json() if n != "concert_singer")
    assert client.post("/api/v1/execute", json={"query": "SELECT 1", "db_id": other}).status_code == 409


def test_executor_timeout_and_blobs(tmp_path):
    db = _make_db(tmp_path / "t.sqlite")
    slow = "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) SELECT count(*) FROM c"
    with pytest.raises(ExecutionError, match="longer than"):
        execute_readonly(db, slow, timeout_s=0.2)
    res = execute_readonly(db, "SELECT x'00ff' AS b")
    assert res["rows"][0][0].startswith("<blob 2 bytes")


# ---------------------------------------------------------------------- NL2SQL jobs
def test_nl2sql_job_runs_and_is_recorded(client):
    ctx = client.app.state.ctx
    from services.nl2sql import NL2SQLService
    ctx.generator_name = "scripted"
    ctx._nl2sql = NL2SQLService(ScriptedGenerator("SELECT nme FROM singer", ["SELECT name FROM singer"]), ctx.diagnosis)
    r = client.post("/api/v1/nl2sql/jobs", headers=CLIENT, json={"question": "singer names?", "database_schema": MUSIC})
    assert r.status_code == 202
    job = r.json()
    for _ in range(100):
        job = client.get(f"/api/v1/nl2sql/jobs/{job['id']}", headers=CLIENT).json()
        if job["status"] in ("done", "error"):
            break
        time.sleep(0.05)
    assert job["status"] == "done", job
    assert job["result"]["sql"] == "SELECT name FROM singer" and job["result"]["status"] == "valid_alternative"
    assert client.get(f"/api/v1/nl2sql/jobs/{job['id']}", headers=OTHER).status_code == 404
    hist = client.get("/api/v1/workspace/history?kind=nl2sql", headers=CLIENT).json()
    assert hist["items"][0]["title"] == "singer names?"
    assert client.delete(f"/api/v1/nl2sql/jobs/{job['id']}", headers=CLIENT).status_code == 409


def test_nl2sql_job_without_generator(client):
    r = client.post("/api/v1/nl2sql/jobs", json={"question": "how many singers?", "database_schema": MUSIC})
    assert r.status_code == 503
    assert client.post("/api/v1/nl2sql/jobs", json={"question": "how many singers?"}).status_code == 422


def test_job_queue_limits_and_cancel():
    q = JobQueue(max_pending=1)
    import threading
    gate = threading.Event()
    first = q.submit("t", lambda job: gate.wait(5))
    for _ in range(100):                  # wait until the worker has picked up the first job
        if first.status == "running":
            break
        time.sleep(0.01)
    queued = q.submit("t", lambda job: 42)
    assert q.position(queued) == 1
    with pytest.raises(QueueFull):
        q.submit("t", lambda job: 0)
    assert q.cancel(queued.id) and q.describe(queued)["status"] == "cancelled"
    failing = q.submit("t", lambda job: 1 / 0)
    gate.set()
    for _ in range(100):
        if failing.finished:
            break
        time.sleep(0.01)
    assert first.status == "done" and failing.status == "error" and "division" in failing.error


# ---------------------------------------------------------------------- results, health and the SPA
def test_results_and_figures(client):
    r = client.get("/api/v1/results")
    if r.status_code == 404:
        pytest.skip("no reports/results.json")
    data = r.json()
    assert "classifiers" in data and isinstance(data["figures"], list)
    if data["figures"]:
        fig = client.get(f"/api/v1/results/figures/{data['figures'][0]}")
        assert fig.status_code == 200 and fig.headers["content-type"] == "image/png"
    assert client.get("/api/v1/results/figures/..%2Fresults.json").status_code == 404
    assert client.get("/api/v1/results/figures/nope.png").status_code == 404


def test_health_reports_web_features(client):
    h = client.get("/api/v1/health").json()
    assert h["workspace_enabled"] and "live_schema_enabled" in h and h["generator_error"] is None


def test_spa_is_served_with_client_side_routes(client):
    root = client.get("/")
    assert root.status_code == 200 and "<div id=root>" in root.text
    assert "Content-Security-Policy" in root.headers and root.headers["X-Frame-Options"] == "DENY"
    deep = client.get("/history")
    assert deep.status_code == 200 and "<div id=root>" in deep.text
    asset = client.get("/assets/app-1234.js")
    assert asset.status_code == 200 and "immutable" in asset.headers["cache-control"]
    assert client.get("/assets/missing.js").status_code == 404
    assert client.get("/api/v1/unknown").status_code == 404
    assert client.get("/../../etc/passwd").status_code in (200, 404)     # never a file outside dist
    assert "root:" not in client.get("/..%2F..%2F..%2Fetc%2Fpasswd").text
    assert client.get("/docs").status_code == 200
