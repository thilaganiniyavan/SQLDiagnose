# app.py
# Clean Architecture: Frameworks & Drivers
# Streamlit UI for the SQLDiagnose API.
#
#   python -m streamlit run frontend/app.py

import difflib
import html
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import requests
import streamlit as st
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_config() -> Dict[str, Any]:
    path = PROJECT_ROOT / "configs" / "frontend_config.yaml"
    cfg = yaml.safe_load(path.read_text()).get("streamlit", {}) if path.exists() else {}
    cfg["api_url"] = os.environ.get("SQLDIAGNOSE_API_URL", cfg.get("api_url", "http://127.0.0.1:8000/api/v1")).rstrip("/")
    return cfg


CFG = load_config()
API = CFG["api_url"]
TIMEOUT = CFG.get("request_timeout_s", 60)

CLASS_COLORS = {
    "CORRECT": "#22c55e", "SYNTAX_ERROR": "#ef4444", "UNKNOWN_TABLE": "#f97316", "UNKNOWN_COLUMN": "#f59e0b",
    "DATATYPE_MISMATCH": "#a855f7", "AMBIGUOUS_REFERENCE": "#06b6d4", "PERMISSION_DENIED": "#e11d48",
    "SEMANTIC_ERROR": "#3b82f6",
}

st.set_page_config(page_title=CFG.get("title", "SQLDiagnose"), page_icon="🩺", layout="wide")
st.markdown("""
<style>
.badge {display:inline-block;padding:4px 12px;border-radius:999px;font-weight:600;color:white;font-size:0.95rem}
.sqlbox {font-family: ui-monospace, SFMono-Regular, Menlo, monospace; background:#0b1220; border:1px solid #334155;
         border-radius:8px; padding:10px 12px; white-space:pre-wrap; word-break:break-word; font-size:0.9rem}
.tok {display:inline-block;margin:2px;padding:2px 5px;border-radius:4px;font-family:ui-monospace,monospace;font-size:0.85rem}
.muted {color:#94a3b8;font-size:0.9rem}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------- API helpers
def api(method: str, path: str, timeout: Optional[float] = None, **kwargs) -> Optional[Any]:
    try:
        r = requests.request(method, f"{API}{path}", timeout=timeout or TIMEOUT, **kwargs)
    except requests.RequestException:
        st.error(f"Cannot reach the API at {API}. Start it with "
                 "`python -m uvicorn deployment.api.main:app --port 8000`.")
        return None
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail")
        except ValueError:
            detail = r.text
        st.error(f"API error {r.status_code}: {detail}")
        return None
    return r.json()


@st.cache_data(ttl=10, show_spinner=False)
def get_health():
    try:
        return requests.get(f"{API}/health", timeout=3).json()
    except (requests.RequestException, ValueError):
        return None


@st.cache_data(ttl=300, show_spinner=False)
def get_example_dbs() -> List[str]:
    try:
        return requests.get(f"{API}/schemas", timeout=5).json()
    except (requests.RequestException, ValueError):
        return []


@st.cache_data(ttl=300, show_spinner=False)
def get_example_schema(db_id: str) -> Optional[Dict]:
    try:
        return requests.get(f"{API}/schemas/{db_id}", timeout=5).json()
    except (requests.RequestException, ValueError):
        return None


def badge(cls: str) -> str:
    return f'<span class="badge" style="background:{CLASS_COLORS.get(cls, "#64748b")}">{html.escape(cls)}</span>'


def sql_box(sql: str) -> str:
    return f'<div class="sqlbox">{html.escape(sql)}</div>'


def diff_html(before: str, after: str) -> str:
    """Word-level diff: removed words struck through in red, added words in green."""
    a, b = before.split(), after.split()
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes():
        if tag == "equal":
            out.append(html.escape(" ".join(a[i1:i2])))
            continue
        if i2 > i1:
            out.append(f'<span style="background:rgba(239,68,68,.25);text-decoration:line-through">'
                       f'{html.escape(" ".join(a[i1:i2]))}</span>')
        if j2 > j1:
            out.append(f'<span style="background:rgba(34,197,94,.3)">{html.escape(" ".join(b[j1:j2]))}</span>')
    return f'<div class="sqlbox">{" ".join(out)}</div>'


# One verified example per error class on the concert_singer database.
EXAMPLES = {
    "Several errors at once": ("SELEC Name, count(*) FORM singr WHERE Age > 'thirty'", []),
    "CORRECT": ("SELECT Name, Country FROM singer WHERE Age > 40 ORDER BY Age DESC", []),
    "SYNTAX_ERROR": ("SELECT Name, Country FORM singer WHERE Age > 40", []),
    "UNKNOWN_TABLE": ("SELECT count(*) FROM singers WHERE Country = 'France'", []),
    "UNKNOWN_COLUMN": ("SELECT Nmae, Age FROM singer ORDER BY Age", []),
    "DATATYPE_MISMATCH": ("SELECT Name FROM singer WHERE Age > 'thirty'", []),
    "AMBIGUOUS_REFERENCE": ("SELECT Singer_ID, Name FROM singer JOIN singer_in_concert "
                            "ON singer.Singer_ID = singer_in_concert.Singer_ID", []),
    "SEMANTIC_ERROR (aggregate in WHERE)": ("SELECT Name FROM singer WHERE Age > avg(Age)", []),
    "SEMANTIC_ERROR (missing join condition)": ("SELECT T2.concert_Name FROM stadium AS T1 JOIN concert AS T2 "
                                                "WHERE T1.Capacity > 5000", []),
    "PERMISSION_DENIED (stadium is restricted)": ("SELECT Name, Capacity FROM stadium", ["stadium"]),
}


def load_example():
    choice = st.session_state.get("example")
    if choice in EXAMPLES:
        query, restricted = EXAMPLES[choice]
        st.session_state.query = query
        st.session_state.schema_source = "Example database"
        st.session_state.db_select = "concert_singer"
        st.session_state.restricted = restricted


def token_html(tokens: List[Dict]) -> str:
    peak = max((abs(t["score"]) for t in tokens), default=1.0) or 1.0
    spans = []
    for t in tokens:
        w = abs(t["score"]) / peak
        color = f"rgba(239,68,68,{0.12 + 0.6 * w:.2f})" if t["score"] > 0 else f"rgba(59,130,246,{0.12 + 0.5 * w:.2f})"
        spans.append(f'<span class="tok" style="background:{color}" title="{t["score"]:+.4f}">{html.escape(t["token"])}</span>')
    return "<div>" + "".join(spans) + "</div>"


# ---------------------------------------------------------------------- session state
ss = st.session_state
ss.setdefault("history", [])
ss.setdefault("custom_schema", None)
ss.setdefault("query", EXAMPLES["Several errors at once"][0])

# Shareable links: ?example=<name>&run=1 or ?q=<sql>&db=<db_id>&run=1&tab=<tab>
_params = st.query_params
if "link_applied" not in ss:
    ss.link_applied = True
    if _params.get("example") in EXAMPLES:
        ss.example = _params["example"]
        load_example()
    elif _params.get("q"):
        ss.query = _params["q"]
        if _params.get("db"):
            ss.schema_source, ss.db_select = "Example database", _params["db"]
    ss.auto_run = _params.get("run") == "1"

# ---------------------------------------------------------------------- sidebar: status + schema context
health = get_health()
with st.sidebar:
    st.header("SQLDiagnose")
    if health:
        st.success("API online")
        if health["model_loaded"]:
            m = health["model"]
            f1 = (m.get("validation") or {}).get("macro_f1")
            st.caption(f"Classifier: `{m.get('backbone')}`" + (f" · val macro-F1 {f1:.3f}" if f1 else ""))
        else:
            st.warning("No classifier checkpoint loaded — diagnoses use the deterministic analyzer only.")
        st.caption(f"Generator: `{health.get('generator') or 'disabled'}`"
                   + (" (loaded)" if health.get("generator_loaded") else " (loads on first use)"))
    else:
        st.error(f"API offline ({API})")

    st.subheader("Database schema")
    dbs = get_example_dbs()
    sources = ["Example database", "Custom schema", "No schema"]
    ss.setdefault("schema_source", sources[0] if dbs else sources[2])
    source = st.radio("Schema source", sources, label_visibility="collapsed", key="schema_source")
    context: Dict[str, Any] = {}
    active_tables: Dict[str, Any] = {}
    if source == "Example database" and dbs:
        default = CFG.get("default_database")
        ss.setdefault("db_select", default if default in dbs else dbs[0])
        db_id = st.selectbox("Database", dbs, key="db_select")
        context["db_id"] = db_id
        info = get_example_schema(db_id)
        active_tables = info["database_schema"] if info else {}
    elif source == "Custom schema":
        if ss.custom_schema:
            st.caption("Using the schema from the *Schema* tab. Edit it below if needed.")
        text = st.text_area("Schema JSON", value=json.dumps(ss.custom_schema or {
            "users": {"columns": {"id": "INTEGER", "name": "TEXT", "age": "INTEGER"}, "primary_keys": ["id"]},
            "orders": {"columns": {"id": "INTEGER", "user_id": "INTEGER", "total": "REAL"}, "primary_keys": ["id"],
                       "foreign_keys": [{"column": "user_id", "target_table": "users", "target_column": "id"}]}},
            indent=1), height=220)
        try:
            active_tables = json.loads(text)
            context["database_schema"] = active_tables
        except json.JSONDecodeError as e:
            st.error(f"Invalid JSON: {e}")
    else:
        st.caption("Without a schema only grammar and schema-independent checks are verified.")

    if active_tables:
        with st.expander(f"Tables ({len(active_tables)})"):
            for t, info in active_tables.items():
                cols = info.get("columns", {})
                cols_txt = ", ".join(f"{c} {ty}" for c, ty in cols.items()) if isinstance(cols, dict) else ", ".join(map(str, cols))
                st.markdown(f"**{t}**: {cols_txt}")
        if any(t not in active_tables for t in ss.get("restricted", [])):
            ss.restricted = []
        restricted = st.multiselect("Restricted tables (access policy)", list(active_tables), key="restricted")
        if restricted:
            context["access_policy"] = {"restricted_tables": restricted, "restricted_columns": []}

    st.subheader("History")
    history_box = st.container()          # filled at the end of the script, after this run is recorded


def restore(query: str):
    st.session_state.query = query


def remember(query: str, cls: str):
    ss.history = [h for h in ss.history if h["query"] != query]
    ss.history.insert(0, {"query": query, "class": cls})
    del ss.history[CFG.get("history_limit", 15):]


# ---------------------------------------------------------------------- tabs
st.title("SQL diagnosis, repair and NL→SQL")
st.caption("Classifies a query into one of eight error classes, explains why, and returns a repair that has been "
           "verified against the schema. A deterministic analyzer provides verified verdicts; a fine-tuned code "
           "transformer adds a learned opinion with token-level explanations.")
tab_diag, tab_nl, tab_batch, tab_schema, tab_results, tab_stats = st.tabs(
    ["Diagnose & repair", "Question → SQL", "Batch", "Schema", "Results", "Service"])

# ---- Diagnose & repair
with tab_diag:
    left, right = st.columns([1, 1], gap="large")
    with left:
        st.selectbox("Load an example", ["—"] + list(EXAMPLES), key="example", on_change=load_example)
        query = st.text_area("SQL query", key="query", height=180)
        c1, c2 = st.columns(2)
        explain = c1.toggle("Token attributions", value=True, disabled=not (health and health.get("model_loaded")))
        method = c2.selectbox("Method", ["gxi", "ig"], format_func=lambda m: {"gxi": "Gradient × input (fast)",
                                                                               "ig": "Integrated gradients"}[m],
                              disabled=not explain)
        run = st.button("Diagnose and repair", type="primary", width="stretch") or ss.pop("auto_run", False)
    with right:
        if run and query.strip():
            with st.spinner("Analyzing ..."):
                diag = api("POST", "/diagnose", json={"query": query, "explain": explain, "explain_method": method, **context})
                rep = api("POST", "/repair", json={"query": query, **context}) if diag and diag["is_error"] else None
            if diag:
                remember(query, diag["error_class"])
                st.markdown(f"{badge(diag['error_class'])} &nbsp; <span class='muted'>decided by "
                            f"{diag['decided_by']} · {diag['latency_ms']:.0f} ms</span>", unsafe_allow_html=True)
                st.write(diag["description"])
                issues = (diag.get("analysis") or {}).get("issues", [])
                for issue in issues:
                    st.markdown(f"- **{issue['error_class']}** — {html.escape(issue['message'])}")
                for note in diag.get("notes", []):
                    st.info(note)

                if rep:
                    r = rep["repair"]
                    st.subheader("Repair")
                    if r["success"]:
                        st.success("Verified fix — the repaired query passes every check.")
                    else:
                        st.warning(f"No complete fix found (remaining: {r['remaining_error']}).")
                    if r["repaired_query"]:
                        st.markdown(diff_html(query, r["repaired_query"]), unsafe_allow_html=True)
                    for i, s in enumerate(r["steps"], 1):
                        st.markdown(f"{i}. `{s['error_class']}` {html.escape(s['description'])}")
                    if not r["success"]:
                        st.caption(r["explanation"])

                model = diag.get("model")
                if model:
                    st.subheader("Model")
                    probs = pd.DataFrame({"class": list(model["probabilities"]),
                                          "probability": list(model["probabilities"].values())}).sort_values("probability")
                    st.bar_chart(probs, x="class", y="probability", horizontal=True, height=240)
                exp = diag.get("explanation")
                if exp and "query_tokens" in exp:
                    st.markdown(f"**Why {exp['target_class']}?** "
                                "<span class='muted'>red pushes towards the prediction, blue against</span>",
                                unsafe_allow_html=True)
                    st.markdown(token_html(exp["query_tokens"]), unsafe_allow_html=True)
                elif exp and "error" in exp:
                    st.caption(exp["error"])
        else:
            st.caption("Enter a query and press *Diagnose and repair*. Pick the database in the sidebar.")

# ---- NL -> SQL
with tab_nl:
    if "db_id" not in context and "database_schema" not in context:
        st.info("Choose an example database or a custom schema in the sidebar first.")
    question = st.text_input("Question", value="How many singers are older than 30?")
    k = st.slider("Candidates", 1, 5, 3)
    if st.button("Generate SQL", type="primary") and question.strip():
        with st.spinner("Generating, verifying and repairing (the first request loads the model) ..."):
            res = api("POST", "/nl2sql", timeout=CFG.get("nl2sql_timeout_s", 180),
                      json={"question": question, "num_candidates": k, **context})
        if res:
            status = {"valid": "Top candidate is valid", "valid_alternative": "A lower-ranked candidate was valid",
                      "repaired": "Generated SQL was invalid and has been repaired",
                      "invalid": "No valid SQL could be produced"}.get(res["status"], res["status"])
            (st.success if res["status"] != "invalid" else st.error)(status)
            if res["sql"]:
                st.markdown(sql_box(res["sql"]), unsafe_allow_html=True)
            st.dataframe(pd.DataFrame([{"rank": c["rank"], "sql": c["sql"], "confidence": c["confidence"],
                                        "verdict": c["error_class"], "issues": "; ".join(c["issues"])}
                                       for c in res["candidates"]]), hide_index=True, width="stretch")
            if res.get("repair"):
                st.caption(res["repair"]["explanation"])
            if res.get("prompt_truncated"):
                st.warning("The schema was too long for the generator's input and was truncated.")
            st.caption(f"Generator {res['generator']} · {res['latency_ms']:.0f} ms")

# ---- Batch
with tab_batch:
    st.write("Diagnose many queries against the schema selected in the sidebar, or upload a CSV with a "
             "`query` column (and optionally `db_id`).")
    mode = st.radio("Input", ["Paste queries", "Upload CSV"], horizontal=True)
    do_repair = st.checkbox("Repair erroneous queries", value=True)
    results = None
    if mode == "Paste queries":
        text = st.text_area("One query per line", height=160,
                            value="SELECT Name FROM singer\nSELECT Nmae FROM singer\nSELECT count(*) FROM singers")
        if st.button("Run batch", type="primary"):
            queries = [q for q in text.splitlines() if q.strip()]
            results = api("POST", "/batch", json={"queries": queries, "repair": do_repair, **context}) if queries else None
    else:
        up = st.file_uploader("CSV file", type=["csv"])
        if up is not None and st.button("Process file", type="primary"):
            params = {"repair": str(do_repair).lower()}
            if "db_id" in context:
                params["db_id"] = context["db_id"]
            results = api("POST", "/upload", params=params, files={"file": (up.name, up.getvalue(), "text/csv")},
                          timeout=600)
    if results:
        df = pd.DataFrame(results)
        a, b, c = st.columns(3)
        a.metric("Queries", len(df))
        b.metric("With errors", int(df["is_error"].sum()))
        if "repair_success" in df:
            c.metric("Repaired", int(df["repair_success"].fillna(False).sum()))
        st.bar_chart(df["error_class"].value_counts())
        st.dataframe(df, width="stretch", hide_index=True)
        st.download_button("Download results (CSV)", df.to_csv(index=False), "sqldiagnose_results.csv", "text/csv")

# ---- Schema
with tab_schema:
    st.write("Import a schema; it becomes the *Custom schema* in the sidebar.")
    how = st.radio("Source", ["CREATE TABLE statements", "SQLite file", "Live PostgreSQL / MySQL"], horizontal=True)
    parsed = None
    if how == "CREATE TABLE statements":
        dialect = st.selectbox("Dialect", ["sqlite", "postgres", "mysql", "tsql", "oracle", "snowflake", "bigquery"])
        ddl = st.text_area("DDL", height=200, value="CREATE TABLE users (id INT PRIMARY KEY, name VARCHAR(80), age INT);\n"
                                                    "CREATE TABLE orders (id INT PRIMARY KEY, user_id INT REFERENCES users(id), total DECIMAL(10,2));")
        if st.button("Parse DDL", type="primary"):
            parsed = api("POST", "/schemas/parse-ddl", json={"ddl": ddl, "dialect": dialect})
    elif how == "SQLite file":
        up = st.file_uploader("SQLite database", type=["sqlite", "db", "sqlite3"])
        if up is not None and st.button("Read schema", type="primary"):
            parsed = api("POST", "/schemas/parse-sqlite", files={"file": (up.name, up.getvalue(), "application/octet-stream")})
    else:
        engine = st.selectbox("Engine", ["postgresql", "mysql"])
        if engine == "postgresql":
            dsn = st.text_input("libpq connection string", value="dbname=mydb user=postgres host=localhost port=5432")
            conn = {"dsn": dsn}
        else:
            c1, c2 = st.columns(2)
            conn = {"host": c1.text_input("Host", "localhost"), "port": int(c2.number_input("Port", value=3306)),
                    "user": c1.text_input("User", "root"), "password": c2.text_input("Password", type="password"),
                    "database": c1.text_input("Database", "mydb")}
        st.caption("Credentials are sent to the API only for this request and are not stored.")
        if st.button("Connect and read schema", type="primary"):
            parsed = api("POST", "/schemas/parse-live", json={"engine": engine, "connection": conn})
    if parsed:
        ss.custom_schema = parsed["database_schema"]
        st.success(f"Parsed {len(ss.custom_schema)} tables. Select *Custom schema* in the sidebar to use it.")
        st.json(ss.custom_schema, expanded=False)

# ---- Results (read from the evaluation outputs on disk)
with tab_results:
    results_path = PROJECT_ROOT / "reports" / "results.json"
    if not results_path.exists():
        st.info("No evaluation results yet. Run `python -m evaluation.evaluate --model-dir <checkpoint>`.")
    else:
        res = json.loads(results_path.read_text())
        main = res.get("main_model")
        clf = res["classifiers"].get(main, {}) if main else {}
        rep_all = res.get("repair", {}).get("ALL", {})
        nl = res.get("nl2sql") or {}
        st.write(f"Test set: {res['dataset']['test']} queries from {res['dataset']['test_dbs']} databases that never "
                 f"appear in training.")
        k1, k2, k3, k4 = st.columns(4)
        if clf:
            base = res["classifiers"]["TF-IDF + LogReg"]
            k1.metric("Classifier accuracy", f"{100 * clf['accuracy']:.1f}%",
                      f"{100 * (clf['accuracy'] - base['accuracy']):+.1f} vs TF-IDF")
            k2.metric("Macro-F1", f"{100 * clf['macro_f1']:.1f}")
        if rep_all:
            k3.metric("Verified repairs", f"{100 * rep_all['verified_rate']:.1f}%",
                      f"{100 * rep_all['exact_rate']:.1f}% exact", delta_color="off")
        if nl:
            k4.metric("NL→SQL valid SQL", f"{100 * nl['final_validity']:.1f}%",
                      f"{100 * (nl['final_validity'] - nl['raw_validity']):+.1f} vs raw generation")
        st.subheader("Classification")
        st.dataframe(pd.DataFrame([{"system": n, "accuracy": round(100 * v["accuracy"], 1),
                                    "macro-F1": round(100 * v["macro_f1"], 1),
                                    "ROC-AUC": round(100 * (v.get("macro_roc_auc") or 0), 1)}
                                   for n, v in res["classifiers"].items()]), hide_index=True, width="stretch")
        fig = PROJECT_ROOT / "reports" / "figures"
        c1, c2 = st.columns(2)
        for col, name, cap in ((c1, "confusion_matrix.png", "Confusion matrix"),
                               (c2, "per_class_f1.png", "Per-class F1"),
                               (c1, "repair_by_class.png", "Repair by class"),
                               (c2, "nl2sql_pipeline.png", "NL→SQL pipeline"),
                               (c1, "training_curve.png", "Training curve"),
                               (c2, "reliability.png", "Calibration")):
            if (fig / name).exists():
                col.image(str(fig / name), caption=cap)
        st.caption("Full report: reports/evaluation_report.md")

# ---- Service
with tab_stats:
    m = api("GET", "/metrics") if health else None
    if m:
        a, b, c, d = st.columns(4)
        a.metric("Diagnoses", m["diagnoses"])
        b.metric("Mean latency", f"{m['mean_diagnosis_latency_ms']:.0f} ms")
        c.metric("Repairs", m["repairs"])
        d.metric("Successful repairs", m["repairs_successful"])
        counts = pd.Series(m["class_counts"])
        if counts.sum():
            st.bar_chart(counts[counts > 0])
        st.caption(f"Uptime {m['uptime_s'] / 60:.1f} min · requests {m['requests']}")
    if health and health.get("model"):
        st.subheader("Loaded classifier")
        st.json(health["model"], expanded=False)
    labels = api("GET", "/labels") if health else None
    if labels:
        st.subheader("Error classes")
        st.dataframe(pd.DataFrame(labels), hide_index=True, width="stretch")


# ---- sidebar history (rendered last so it includes the query just run)
with history_box:
    if not ss.history:
        st.caption("Nothing yet.")
    for i, h in enumerate(ss.history):
        st.button(f"{h['class']}: {h['query'][:32]}", key=f"hist{i}", width="stretch",
                  on_click=restore, args=(h["query"],))
