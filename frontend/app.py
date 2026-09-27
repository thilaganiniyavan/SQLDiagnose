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

st.set_page_config(page_title=CFG.get("title", "SQLDiagnose"), page_icon="🩺", layout="wide", initial_sidebar_state="expanded")
st.markdown("""
<style>
:root {
  --primary: #0f172a;
  --primary-light: #1e293b;
  --accent: #3b82f6;
  --accent-hover: #2563eb;
  --success: #10b981;
  --error: #ef4444;
  --warning: #f59e0b;
  --border: #334155;
  --bg-dark: #0f172a;
  --bg-darker: #020617;
  --text-primary: #f1f5f9;
  --text-secondary: #cbd5e1;
}

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
  color: var(--text-primary);
}

/* Main container styling */
.main {
  background: var(--bg-dark);
  color: var(--text-primary);
}

/* Header styling */
header {
  background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
  border-bottom: 1px solid var(--border);
  padding: 20px 0;
}

/* Card styling */
.metric-card {
  background: linear-gradient(135deg, #1e293b 0%, #164e63 100%);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px;
  margin: 10px 0;
  transition: all 0.3s ease;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
}

.metric-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 12px 16px rgba(59, 130, 246, 0.2);
  border-color: var(--accent);
}

/* Badge styling */
.badge {
  display: inline-block;
  padding: 8px 16px;
  border-radius: 20px;
  font-weight: 600;
  color: white;
  font-size: 0.85rem;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}

.badge.correct {
  background: linear-gradient(135deg, #10b981 0%, #059669 100%);
}

.badge.error {
  background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
}

.badge.warning {
  background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
}

/* SQL Box styling */
.sqlbox {
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', ui-monospace, SFMono-Regular, monospace;
  background: linear-gradient(135deg, #020617 0%, #0f172a 100%);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 0.9rem;
  line-height: 1.6;
  color: #e2e8f0;
  box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.3);
}

.sqlbox:hover {
  border-color: var(--accent);
  box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.3), 0 0 20px rgba(59, 130, 246, 0.1);
}

/* Token styling */
.tok {
  display: inline-block;
  margin: 2px;
  padding: 4px 8px;
  border-radius: 6px;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', ui-monospace, monospace;
  font-size: 0.85rem;
  font-weight: 500;
  transition: all 0.2s ease;
}

.tok:hover {
  transform: scale(1.05);
}

/* Text styling */
.muted {
  color: var(--text-secondary);
  font-size: 0.9rem;
  letter-spacing: 0.3px;
}

/* Info boxes */
.info-box {
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.1) 0%, rgba(59, 130, 246, 0.05) 100%);
  border-left: 4px solid var(--accent);
  border-right: 1px solid var(--border);
  border-top: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
  padding: 16px;
  border-radius: 8px;
  margin: 16px 0;
  backdrop-filter: blur(10px);
}

.tip-box {
  background: linear-gradient(135deg, rgba(16, 185, 129, 0.1) 0%, rgba(16, 185, 129, 0.05) 100%);
  border-left: 4px solid var(--success);
  border-right: 1px solid var(--border);
  border-top: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
  padding: 16px;
  border-radius: 8px;
  margin: 16px 0;
  backdrop-filter: blur(10px);
}

/* Tabs styling */
[data-testid="stTabs"] {
  background: transparent;
  border-radius: 12px;
  overflow: hidden;
}

[data-testid="stTabs"] [data-testid="stTabBar"] {
  background: linear-gradient(90deg, #1e293b 0%, #0f172a 100%);
  border-bottom: 2px solid var(--border);
}

[data-testid="stTabs"] button[aria-selected="true"] {
  color: var(--accent) !important;
  border-bottom: 3px solid var(--accent) !important;
}

/* Button styling */
.stButton > button {
  background: linear-gradient(135deg, var(--accent) 0%, var(--accent-hover) 100%) !important;
  color: white !important;
  border: none !important;
  border-radius: 8px !important;
  padding: 12px 24px !important;
  font-weight: 600 !important;
  transition: all 0.3s ease !important;
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3) !important;
  font-size: 0.95rem !important;
  letter-spacing: 0.3px !important;
}

.stButton > button:hover {
  transform: translateY(-2px) !important;
  box-shadow: 0 8px 20px rgba(59, 130, 246, 0.4) !important;
}

.stButton > button:active {
  transform: translateY(0) !important;
}

/* Input styling */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea,
.stSelectbox > div > div > select,
.stNumberInput > div > div > input {
  background: var(--primary-light) !important;
  border: 1px solid var(--border) !important;
  border-radius: 8px !important;
  color: var(--text-primary) !important;
  padding: 12px !important;
  transition: all 0.3s ease !important;
  font-size: 0.95rem !important;
}

.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus,
.stSelectbox > div > div > select:focus,
.stNumberInput > div > div > input:focus {
  border-color: var(--accent) !important;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1) !important;
  background: rgba(30, 41, 59, 0.8) !important;
}

/* Sidebar styling */
[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #1e293b 0%, #0f172a 100%);
  border-right: 1px solid var(--border);
}

[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
  padding-top: 20px;
}

/* Expander styling */
[data-testid="stExpander"] {
  border: 1px solid var(--border) !important;
  border-radius: 8px !important;
  background: rgba(30, 41, 59, 0.5) !important;
  margin: 8px 0 !important;
}

[data-testid="stExpander"] [data-testid="stExpanderDetails"] {
  padding: 16px !important;
}

/* Divider styling */
hr {
  border: none;
  border-top: 1px solid var(--border);
  margin: 24px 0;
}

/* Markdown headings */
h1, h2, h3, h4, h5, h6 {
  color: var(--text-primary) !important;
  font-weight: 700 !important;
  letter-spacing: -0.5px !important;
}

h1 {
  background: linear-gradient(135deg, #3b82f6 0%, #06b6d4 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  margin-bottom: 24px !important;
  font-size: 2.5rem !important;
}

h2 {
  margin-top: 24px !important;
  margin-bottom: 16px !important;
  font-size: 1.5rem !important;
}

h3 {
  margin-top: 20px !important;
  margin-bottom: 12px !important;
  font-size: 1.2rem !important;
  color: #e0f2fe !important;
}

/* Success/Error/Warning messages */
[data-testid="stAlert"] {
  border-radius: 8px !important;
  border-left: 4px solid !important;
  padding: 16px !important;
  margin: 12px 0 !important;
  backdrop-filter: blur(10px) !important;
}

/* Metric styling */
[data-testid="metric-container"] {
  background: linear-gradient(135deg, #1e293b 0%, #164e63 100%) !important;
  border: 1px solid var(--border) !important;
  border-radius: 12px !important;
  padding: 20px !important;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.2) !important;
}

/* Dataframe styling */
[data-testid="stDataFrame"] {
  border-radius: 8px !important;
  overflow: hidden !important;
}

/* Loading spinner */
.stSpinner {
  color: var(--accent) !important;
}

/* Scrollbar styling */
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: var(--primary-light);
}

::-webkit-scrollbar-thumb {
  background: var(--accent);
  border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
  background: var(--accent-hover);
}

/* Animation for page load */
@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

[data-testid="stContainer"] {
  animation: slideIn 0.4s ease-out;
}

/* Professional color scheme for different states */
.status-correct { color: var(--success); }
.status-error { color: var(--error); }
.status-warning { color: var(--warning); }
.status-info { color: var(--accent); }
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
    badge_class = "correct" if cls == "CORRECT" else ("error" if "ERROR" in cls or cls in ["SYNTAX_ERROR", "UNKNOWN_TABLE", "UNKNOWN_COLUMN", "DATATYPE_MISMATCH", "AMBIGUOUS_REFERENCE", "PERMISSION_DENIED", "SEMANTIC_ERROR"] else "warning")
    return f'<span class="badge {badge_class}">{html.escape(cls)}</span>'


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
    st.header("⚙️ Settings")

    with st.expander("🔧 System Status", expanded=True):
        if health:
            st.success("✅ API is ready")
            if health["model_loaded"]:
                m = health["model"]
                f1 = (m.get("validation") or {}).get("macro_f1")
                st.caption(f"**Classifier**: {m.get('backbone')}" + (f" • **Accuracy**: {f1:.1%}" if f1 else ""))
            else:
                st.info("📌 Rule-based analyzer active (no AI model)")
            st.caption(f"**Generator**: {health.get('generator') or 'Disabled'}" +
                       (" ✓" if health.get("generator_loaded") else " (loads on first use)"))
        else:
            st.error(f"❌ API offline at {API}")

    st.markdown("---")
    st.markdown("### 📂 Pick Your Database")
    dbs = get_example_dbs()
    sources = ["📊 Use an example", "✏️ Custom schema", "❌ No schema"]
    ss.setdefault("schema_source", sources[0] if dbs else sources[2])
    source = st.radio("Schema source:", sources, label_visibility="collapsed", key="schema_source")
    context: Dict[str, Any] = {}
    active_tables: Dict[str, Any] = {}
    if source == "📊 Use an example" and dbs:
        default = CFG.get("default_database")
        ss.setdefault("db_select", default if default in dbs else dbs[0])
        db_id = st.selectbox("Which example database?", dbs, key="db_select",
                            help=f"We have {len(dbs)} real databases from academic research")
        context["db_id"] = db_id
        info = get_example_schema(db_id)
        active_tables = info["database_schema"] if info else {}
    elif source == "✏️ Custom schema":
        st.caption("📝 Paste your database structure as JSON (or use the *Schema* tab to import from DDL/files)")
        text = st.text_area("Your schema (JSON):", value=json.dumps(ss.custom_schema or {
            "users": {"columns": {"id": "INTEGER", "name": "TEXT", "age": "INTEGER"}, "primary_keys": ["id"]},
            "orders": {"columns": {"id": "INTEGER", "user_id": "INTEGER", "total": "REAL"}, "primary_keys": ["id"],
                       "foreign_keys": [{"column": "user_id", "target_table": "users", "target_column": "id"}]}},
            indent=1), height=200, label_visibility="collapsed")
        try:
            active_tables = json.loads(text)
            context["database_schema"] = active_tables
        except json.JSONDecodeError as e:
            st.error(f"❌ Invalid JSON: {e}")
    else:
        st.info("💡 Without a schema, we can only check grammar and basic SQL rules.")

    if active_tables:
        with st.expander(f"📋 Your tables ({len(active_tables)})", expanded=True):
            for t, info in active_tables.items():
                cols = info.get("columns", {})
                cols_txt = ", ".join(f"{c} {ty}" for c, ty in cols.items()) if isinstance(cols, dict) else ", ".join(map(str, cols))
                st.caption(f"**{t}**: {cols_txt}")

        st.markdown("**🔒 Access control** (optional)")
        if any(t not in active_tables for t in ss.get("restricted", [])):
            ss.restricted = []
        restricted = st.multiselect("Mark these tables as restricted:", list(active_tables), key="restricted",
                                    help="Queries accessing these tables will be flagged as PERMISSION_DENIED")
        if restricted:
            context["access_policy"] = {"restricted_tables": restricted, "restricted_columns": []}

    st.markdown("---")
    st.markdown("### 📜 Recent Queries")
    history_box = st.container()          # filled at the end of the script, after this run is recorded


def restore(query: str):
    st.session_state.query = query


def remember(query: str, cls: str):
    ss.history = [h for h in ss.history if h["query"] != query]
    ss.history.insert(0, {"query": query, "class": cls})
    del ss.history[CFG.get("history_limit", 15):]


# ---------------------------------------------------------------------- tabs
st.markdown("""
<div style="background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #0f4c75 100%);
            border-radius: 16px; padding: 40px; margin-bottom: 30px;
            border: 1px solid #334155; box-shadow: 0 20px 40px rgba(59, 130, 246, 0.1);">
    <h1 style="margin: 0 0 16px 0; font-size: 2.5rem;
               background: linear-gradient(135deg, #3b82f6 0%, #06b6d4 100%);
               -webkit-background-clip: text; -webkit-text-fill-color: transparent;
               background-clip: text;">
        🩺 SQLDiagnose
    </h1>
    <p style="color: #cbd5e1; font-size: 1.1rem; margin: 0; line-height: 1.6;">
        <strong>Enterprise-grade SQL error detection, repair, and generation.</strong>
        Check your queries, get instant fixes, and transform questions into SQL.
    </p>
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 16px; margin-top: 24px;">
        <div style="background: rgba(59, 130, 246, 0.1); border-left: 4px solid #3b82f6;
                    padding: 12px 16px; border-radius: 8px;">
            <p style="color: #3b82f6; font-weight: 600; margin: 0; font-size: 0.9rem;">✓ Query Diagnosis</p>
            <p style="color: #cbd5e1; font-size: 0.85rem; margin: 4px 0 0 0;">8 error classes detected</p>
        </div>
        <div style="background: rgba(16, 185, 129, 0.1); border-left: 4px solid #10b981;
                    padding: 12px 16px; border-radius: 8px;">
            <p style="color: #10b981; font-weight: 600; margin: 0; font-size: 0.9rem;">✓ Auto Repair</p>
            <p style="color: #cbd5e1; font-size: 0.85rem; margin: 4px 0 0 0;">Verified fixes</p>
        </div>
        <div style="background: rgba(59, 130, 246, 0.1); border-left: 4px solid #3b82f6;
                    padding: 12px 16px; border-radius: 8px;">
            <p style="color: #3b82f6; font-weight: 600; margin: 0; font-size: 0.9rem;">✓ NL→SQL</p>
            <p style="color: #cbd5e1; font-size: 0.85rem; margin: 4px 0 0 0;">English to SQL</p>
        </div>
        <div style="background: rgba(248, 113, 113, 0.1); border-left: 4px solid #ef4444;
                    padding: 12px 16px; border-radius: 8px;">
            <p style="color: #ef4444; font-weight: 600; margin: 0; font-size: 0.9rem;">✓ Batch Testing</p>
            <p style="color: #cbd5e1; font-size: 0.85rem; margin: 4px 0 0 0;">Process 1000s fast</p>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)
tab_diag, tab_nl, tab_batch, tab_schema, tab_results, tab_stats = st.tabs(
    ["Diagnose & repair", "Question → SQL", "Batch", "Schema", "Results", "Service"])

# ---- Diagnose & repair
with tab_diag:
    st.markdown("### Query Analysis")

    col_query, col_opts = st.columns([3, 1])

    with col_query:
        st.markdown("**📋 Load an example or paste your SQL:**")
        st.selectbox("Pick an example:", ["—"] + list(EXAMPLES), key="example", on_change=load_example,
                     help="Quick start with real error examples", label_visibility="collapsed")

        query = st.text_area("Your SQL query:", key="query", height=140,
                            placeholder="e.g., SELECT name FORM users WHERE age > 30\n(Try an example first!)",
                            label_visibility="collapsed")

    with col_opts:
        st.markdown("### ⚙️ Options")
        explain = st.checkbox("Show explanations", value=True, disabled=not (health and health.get("model_loaded")),
                             help="AI token explanations")

        if explain and health and health.get("model_loaded"):
            method = st.selectbox("Method", ["gxi", "ig"], format_func=lambda m: {"gxi": "Fast", "ig": "Detailed"}[m],
                                 label_visibility="collapsed")
        else:
            method = "gxi"

    run = st.button("🔍 Analyze Query", type="primary", use_container_width=True) or ss.pop("auto_run", False)

    st.divider()
    st.markdown("### 📊 Results")
    if run and query.strip():
        with st.spinner("🔍 Checking your query..."):
            diag = api("POST", "/diagnose", json={"query": query, "explain": explain, "explain_method": method, **context})
            rep = api("POST", "/repair", json={"query": query, **context}) if diag and diag["is_error"] else None
        if diag:
            remember(query, diag["error_class"])

            col1, col2 = st.columns([2, 1])
            with col1:
                st.markdown(f"{badge(diag['error_class'])} ", unsafe_allow_html=True)
            with col2:
                st.markdown(f"<span class='muted'>⏱️ {diag['latency_ms']:.0f}ms</span>", unsafe_allow_html=True)

            if diag["error_class"] == "CORRECT":
                st.markdown("""
                <div style="background: linear-gradient(135deg, rgba(16, 185, 129, 0.1) 0%, rgba(16, 185, 129, 0.05) 100%);
                            border: 2px solid #10b981; border-radius: 12px; padding: 20px; margin: 16px 0;">
                    <p style="color: #10b981; font-size: 1.2rem; font-weight: 700; margin: 0;">
                        ✅ Query is Correct
                    </p>
                    <p style="color: #cbd5e1; margin: 8px 0 0 0;">No errors detected. This query will execute successfully.</p>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div style="background: linear-gradient(135deg, rgba(239, 68, 68, 0.1) 0%, rgba(239, 68, 68, 0.05) 100%);
                            border: 2px solid #ef4444; border-radius: 12px; padding: 20px; margin: 16px 0;">
                    <p style="color: #ef4444; font-size: 1.2rem; font-weight: 700; margin: 0;">
                        ❌ {diag['description']}
                    </p>
                </div>
                """, unsafe_allow_html=True)
                issues = (diag.get("analysis") or {}).get("issues", [])
                if issues:
                    st.markdown("<div style='margin: 16px 0;'><strong style='color: #e0f2fe;'>🔍 Issues Found:</strong></div>", unsafe_allow_html=True)
                    for issue in issues:
                        st.markdown(f"""
                        <div style="background: rgba(59, 130, 246, 0.05); border-left: 3px solid #3b82f6;
                                    padding: 12px 16px; margin: 8px 0; border-radius: 6px;">
                            <strong style="color: #3b82f6;">{issue['error_class']}</strong>
                            <p style="color: #cbd5e1; margin: 4px 0 0 0;">{html.escape(issue['message'])}</p>
                        </div>
                        """, unsafe_allow_html=True)
                for note in diag.get("notes", []):
                    st.markdown(f"<div class='info-box'>💡 {note}</div>", unsafe_allow_html=True)

            if rep:
                r = rep["repair"]
                st.divider()
                st.markdown("### 🔧 Here's the fix")
                if r["success"]:
                    st.success("✅ **Verified fix** — This repaired query is 100% correct.")
                else:
                    st.warning(f"⚠️ **Partial fix** — Some issues remain: {r['remaining_error']}")
                if r["repaired_query"]:
                    st.markdown("**Changed query:**")
                    st.markdown(diff_html(query, r["repaired_query"]), unsafe_allow_html=True)

                st.markdown("**What was fixed:**")
                for i, s in enumerate(r["steps"], 1):
                    st.write(f"{i}. **{s['error_class']}** — {html.escape(s['description'])}")

                if not r["success"]:
                    st.info(f"Why not fully fixed: {r['explanation']}")

            with st.expander("📈 AI confidence scores", expanded=False):
                model = diag.get("model")
                if model:
                    probs = pd.DataFrame({"Error type": list(model["probabilities"]),
                                          "Confidence": list(model["probabilities"].values())}).sort_values("Confidence")
                    st.bar_chart(probs, x="Error type", y="Confidence", horizontal=True, height=240)

            with st.expander("🎯 What words caused this error?", expanded=explain):
                exp = diag.get("explanation")
                if exp and "query_tokens" in exp:
                    st.markdown("<span class='muted'>Red = points to error, Blue = against error</span>",
                                unsafe_allow_html=True)
                    st.markdown(token_html(exp["query_tokens"]), unsafe_allow_html=True)
                elif exp and "error" in exp:
                    st.info(exp["error"])
                else:
                    st.caption("No word-level explanation available for this error type.")
    else:
        st.info("💡 **How to use:**\n1. Paste a SQL query (or load an example)\n2. Pick your database in the sidebar\n3. Click 'Check this query'\n4. We'll tell you what's wrong and how to fix it!")

# ---- NL -> SQL
with tab_nl:
    st.markdown("### 🤖 Turn Your Question Into SQL")
    st.markdown("Ask a question in English, and we'll generate the SQL query to answer it.")

    if "db_id" not in context and "database_schema" not in context:
        st.warning("⚠️ **Choose a database first** — Pick one in the sidebar under 'Database schema'")

    question = st.text_input("Ask a question about your data:", value="How many singers are older than 30?",
                            placeholder="e.g., Show me all users from France")

    col1, col2 = st.columns(2)
    with col1:
        k = st.slider("How many options to try?", 1, 5, 3, help="More options = more thorough but slower")

    with col2:
        st.empty()

    if st.button("💡 Generate SQL", type="primary", use_container_width=True) and question.strip():
        with st.spinner("🤖 Generating SQL (first use loads the model, takes ~30s)..."):
            res = api("POST", "/nl2sql", timeout=CFG.get("nl2sql_timeout_s", 180),
                      json={"question": question, "num_candidates": k, **context})
        if res:
            st.divider()
            st.markdown("### 📋 Generated SQL Query")

            status_msgs = {
                "valid": ("✅ Perfect! The generated SQL is valid.", "success"),
                "valid_alternative": ("⚠️ Top choice had issues, but we found a valid alternative.", "warning"),
                "repaired": ("✅ Generated SQL was invalid, but we fixed it.", "success"),
                "invalid": ("❌ We couldn't generate valid SQL.", "error")
            }
            msg, func = status_msgs.get(res["status"], (res["status"], "info"))
            getattr(st, func)(msg)

            if res["sql"]:
                st.markdown("**Best SQL for your question:**")
                st.markdown(sql_box(res["sql"]), unsafe_allow_html=True)

            if res.get("repair"):
                st.info(f"💡 {res['repair']['explanation']}")

            if res.get("prompt_truncated"):
                st.warning("⚠️ Your schema was long so it was truncated (might affect accuracy)")

            with st.expander(f"📊 See all {len(res['candidates'])} options tried", expanded=False):
                st.dataframe(pd.DataFrame([{"Rank": c["rank"], "SQL": c["sql"], "Confidence": f"{c['confidence']*100:.0f}%",
                                            "Valid?": c["error_class"], "Issues": "; ".join(c["issues"]) if c["issues"] else "—"}
                                           for c in res["candidates"]]), hide_index=True, use_container_width=True)

            st.caption(f"⏱️ {res['latency_ms']:.0f}ms • Generator: {res['generator']}")

# ---- Batch
with tab_batch:
    st.markdown("### 🚀 Check Many Queries at Once")
    st.markdown("Test hundreds of queries in seconds. Either paste them one per line, or upload a CSV file.")

    mode = st.radio("How would you like to input queries?", ["📝 Paste queries", "📁 Upload CSV file"], horizontal=True)

    col1, col2 = st.columns(2)
    with col1:
        do_repair = st.checkbox("Also fix erroneous queries?", value=True, help="Automatic repair takes extra time")

    results = None
    if mode == "📝 Paste queries":
        st.markdown("**Enter one SQL query per line:**")
        text = st.text_area("Your queries:", height=160, label_visibility="collapsed",
                            value="SELECT Name FROM singer\nSELECT Nmae FROM singer\nSELECT count(*) FROM singers",
                            placeholder="SELECT * FROM users\nSELECT id FROM orders\nSELECT * FROM unknown_table")
        if st.button("🔍 Check all queries", type="primary", use_container_width=True):
            queries = [q for q in text.splitlines() if q.strip()]
            if queries:
                with st.spinner(f"Checking {len(queries)} queries..."):
                    results = api("POST", "/batch", json={"queries": queries, "repair": do_repair, **context})
            else:
                st.error("Please enter at least one query")
    else:
        st.markdown("**CSV file format:** Column named `query` with your SQL. Optional: `db_id` column for different databases.")
        up = st.file_uploader("Choose a CSV file:", type=["csv"], label_visibility="collapsed")
        if up is not None and st.button("📊 Process file", type="primary", use_container_width=True):
            params = {"repair": str(do_repair).lower()}
            if "db_id" in context:
                params["db_id"] = context["db_id"]
            with st.spinner("Processing file..."):
                results = api("POST", "/upload", params=params, files={"file": (up.name, up.getvalue(), "text/csv")},
                              timeout=600)

    if results:
        st.divider()
        st.markdown("### 📊 Results Summary")
        df = pd.DataFrame(results)
        a, b, c = st.columns(3)
        a.metric("Total queries", len(df), help="How many queries you tested")
        b.metric("Queries with errors", int(df["is_error"].sum()),
                help=f"{100*df['is_error'].sum()/len(df):.0f}% error rate")
        if "repair_success" in df:
            repaired = int(df["repair_success"].fillna(False).sum())
            c.metric("Successfully repaired", repaired, help=f"{100*repaired/df['is_error'].sum():.0f}% of errors fixed")

        st.markdown("**Error distribution:**")
        st.bar_chart(df["error_class"].value_counts())

        st.markdown("**Detailed results:**")
        st.dataframe(df, use_container_width=True, hide_index=True)

        st.download_button("⬇️ Download as CSV", df.to_csv(index=False), "sqldiagnose_results.csv", "text/csv")

# ---- Schema
with tab_schema:
    st.markdown("### 📂 Import Your Database Schema")
    st.markdown("Load your database structure from multiple sources. Once imported, it will appear in the sidebar as 'Custom schema'.")

    how = st.radio("How do you want to import?",
                   ["📝 SQL CREATE statements", "📁 SQLite file", "🔌 Live database connection"],
                   horizontal=False, label_visibility="collapsed")

    parsed = None
    st.divider()

    if how == "📝 SQL CREATE statements":
        st.markdown("**Paste your CREATE TABLE statements:**")
        dialect = st.selectbox("SQL Dialect:", ["sqlite", "postgres", "mysql", "tsql", "oracle", "snowflake", "bigquery"],
                              help="Which SQL dialect are your statements in?")
        ddl = st.text_area("Your SQL:", height=200, label_visibility="collapsed",
                          value="CREATE TABLE users (id INT PRIMARY KEY, name VARCHAR(80), age INT);\n"
                                "CREATE TABLE orders (id INT PRIMARY KEY, user_id INT REFERENCES users(id), total DECIMAL(10,2));",
                          placeholder="CREATE TABLE users (\n  id INT PRIMARY KEY,\n  name VARCHAR(80)\n);")
        if st.button("✅ Parse SQL", type="primary", use_container_width=True):
            with st.spinner("Parsing..."):
                parsed = api("POST", "/schemas/parse-ddl", json={"ddl": ddl, "dialect": dialect})

    elif how == "📁 SQLite file":
        st.markdown("**Upload a .sqlite or .db file:**")
        up = st.file_uploader("Choose SQLite file:", type=["sqlite", "db", "sqlite3"], label_visibility="collapsed")
        if up is not None and st.button("📖 Read schema", type="primary", use_container_width=True):
            with st.spinner("Reading..."):
                parsed = api("POST", "/schemas/parse-sqlite", files={"file": (up.name, up.getvalue(), "application/octet-stream")})

    else:
        st.markdown("**Connect to a live database:**")
        engine = st.selectbox("Database type:", ["postgresql", "mysql"], label_visibility="collapsed")

        if engine == "postgresql":
            dsn = st.text_input("Connection string:", value="dbname=mydb user=postgres host=localhost port=5432",
                              placeholder="dbname=mydb user=postgres host=localhost")
            conn = {"dsn": dsn}
        else:
            c1, c2 = st.columns(2)
            conn = {"host": c1.text_input("Host:", "localhost"), "port": int(c2.number_input("Port:", value=3306)),
                    "user": c1.text_input("User:", "root"), "password": c2.text_input("Password:", type="password"),
                    "database": c1.text_input("Database:", "mydb")}

        st.info("🔒 Your credentials are sent only for this request and are not stored.")
        if st.button("🔌 Connect & import", type="primary", use_container_width=True):
            with st.spinner("Connecting..."):
                parsed = api("POST", "/schemas/parse-live", json={"engine": engine, "connection": conn})

    if parsed:
        st.divider()
        ss.custom_schema = parsed["database_schema"]
        st.success(f"✅ **Imported {len(ss.custom_schema)} tables!**\n\nNow select 'Custom schema' in the sidebar to use it.")
        with st.expander("Preview your schema", expanded=True):
            st.json(ss.custom_schema, expanded=False)

# ---- Results (read from the evaluation outputs on disk)
with tab_results:
    st.markdown("### 📈 How Accurate Is SQLDiagnose?")
    st.markdown("This shows how well our AI models perform on real databases.")

    results_path = PROJECT_ROOT / "reports" / "results.json"
    if not results_path.exists():
        st.warning("📌 No evaluation results found. Run `make evaluate` to generate them.")
    else:
        res = json.loads(results_path.read_text())
        main = res.get("main_model")
        clf = res["classifiers"].get(main, {}) if main else {}
        rep_all = res.get("repair", {}).get("ALL", {})
        nl = res.get("nl2sql") or {}

        st.markdown(f"**Test data:** {res['dataset']['test']} queries tested from {res['dataset']['test_dbs']} different databases (never seen during training)")

        st.divider()
        st.markdown("### 🎯 Key Results")

        k1, k2, k3, k4 = st.columns(4)
        if clf:
            base = res["classifiers"]["TF-IDF + LogReg"]
            k1.metric("Error Detection", f"{100 * clf['accuracy']:.1f}%",
                      f"+{100 * (clf['accuracy'] - base['accuracy']):.1f}% vs simple method")
            k2.metric("Precision (F1)", f"{100 * clf['macro_f1']:.1f}%", help="Consistency across all 8 error types")
        if rep_all:
            k3.metric("Repair Success", f"{100 * rep_all['verified_rate']:.1f}%",
                      f"{100 * rep_all['exact_rate']:.1f}% perfect fixes", delta_color="off")
        if nl:
            k4.metric("SQL Generation", f"{100 * nl['final_validity']:.1f}%",
                      f"+{100 * (nl['final_validity'] - nl['raw_validity']):.1f}% after fixing")

        st.divider()
        st.markdown("### 📊 System Comparison")
        st.markdown("How does SQLDiagnose compare to other methods?")
        st.dataframe(pd.DataFrame([{"System": n, "Accuracy": f"{100 * v['accuracy']:.1f}%",
                                    "Consistency (F1)": f"{100 * v['macro_f1']:.1f}%",
                                    "AUC Score": f"{100 * (v.get('macro_roc_auc') or 0):.1f}%"}
                                   for n, v in res["classifiers"].items()]), hide_index=True, use_container_width=True)

        st.divider()
        st.markdown("### 📸 Visual Breakdown")
        fig = PROJECT_ROOT / "reports" / "figures"
        c1, c2 = st.columns(2)
        for col, name, cap in ((c1, "confusion_matrix.png", "What errors were confused?"),
                               (c2, "per_class_f1.png", "Accuracy by error type"),
                               (c1, "repair_by_class.png", "Repair success by error"),
                               (c2, "nl2sql_pipeline.png", "Question→SQL performance"),
                               (c1, "training_curve.png", "Training progress"),
                               (c2, "reliability.png", "Calibration")):
            if (fig / name).exists():
                col.image(str(fig / name), caption=cap)

        with st.expander("📄 Read the full technical report"):
            st.markdown("[Full evaluation report](reports/evaluation_report.md)")
            st.markdown("[Research paper draft](reports/paper_draft.md)")

# ---- Service
with tab_stats:
    st.markdown("### 📊 Service Status & Activity")
    st.markdown("Real-time statistics about the running SQLDiagnose service.")

    m = api("GET", "/metrics") if health else None
    if m:
        st.divider()
        st.markdown("### 📈 Activity This Session")
        a, b, c, d = st.columns(4)
        a.metric("Diagnoses run", m["diagnoses"], help="How many queries you've checked")
        b.metric("Speed", f"{m['mean_diagnosis_latency_ms']:.0f} ms", help="Average time to diagnose a query")
        c.metric("Repairs attempted", m["repairs"], help="How many broken queries we tried to fix")
        d.metric("Fixed", m["repairs_successful"], help=f"{100*m['repairs_successful']/max(m['repairs'],1):.0f}% success rate")

        st.markdown("**Errors found in this session:**")
        counts = pd.Series(m["class_counts"])
        if counts.sum():
            st.bar_chart(counts[counts > 0])
        else:
            st.info("No queries checked yet!")

        st.caption(f"⏱️ Uptime: {m['uptime_s'] / 60:.1f} min • Total requests: {m['requests']}")

    st.divider()
    st.markdown("### 🤖 AI Model Info")
    if health and health.get("model"):
        with st.expander("Classifier details", expanded=False):
            model_info = health.get("model", {})
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Model", model_info.get('backbone', 'Unknown'))
                st.metric("Training F1", f"{(model_info.get('validation', {}).get('macro_f1', 0)):.1%}")
            with col2:
                st.metric("Parameters", f"{model_info.get('num_parameters', 0):,}")
                if "checkpoint_size_mb" in model_info:
                    st.metric("Size on disk", f"{model_info['checkpoint_size_mb']:.0f} MB")

    st.divider()
    st.markdown("### 📋 The 8 Error Classes")
    labels = api("GET", "/labels") if health else None
    if labels:
        label_df = pd.DataFrame(labels)
        st.dataframe(label_df, hide_index=True, use_container_width=True)
    else:
        st.info("Error class definitions not available")


# ---- sidebar history (rendered last so it includes the query just run)
with history_box:
    if not ss.history:
        st.caption("🚀 Check your first query to see history here")
    else:
        for i, h in enumerate(ss.history):
            label = f"✅ {h['class']}" if h['class'] == "CORRECT" else f"❌ {h['class']}"
            st.button(f"{label}: {h['query'][:28]}", key=f"hist{i}", use_container_width=True,
                      on_click=restore, args=(h["query"],))
