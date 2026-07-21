# app.py
# Clean Architecture: Frameworks & Drivers
# Comprehensive Streamlit Dashboard exposing all NLP SQL classification, repair, NL2SQL, schema parsing, and telemetry services.

import streamlit as st
import requests
import json
import yaml
import io
import tempfile
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
from pathlib import Path
from typing import Dict, Any, List
from datasets.schema_parser import DatabaseSchemaParser

# 1. Set Page Config & Rich Aesthetics
st.set_page_config(
    page_title="SQL Diagnostics, Repair & NL2SQL Platform",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for glassmorphism styling and dark mode badges
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        background: linear-gradient(90deg, #3b82f6, #8b5cf6);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.0rem;
        color: #94a3b8;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background: rgba(30, 41, 59, 0.7);
        border: 1px solid #334155;
        border-radius: 10px;
        padding: 15px;
        text-align: center;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    .status-badge-ok {
        background-color: #059669;
        color: white;
        padding: 4px 8px;
        border-radius: 6px;
        font-weight: 600;
    }
    .status-badge-err {
        background-color: #dc2626;
        color: white;
        padding: 4px 8px;
        border-radius: 6px;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

# 2. Load Configuration
def load_config() -> dict:
    project_root = Path(__file__).resolve().parents[1]
    config_path = project_root / "configs" / "frontend_config.yaml"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {
        "streamlit": {
            "title": "SQL Error Classifier Panel",
            "api_url": "http://127.0.0.1:8000",
            "show_confidence_threshold": 0.15,
            "analytics": {"enable_history_tracking": True, "history_limit": 10}
        }
    }

CONFIG = load_config()
API_BASE_URL = CONFIG["streamlit"].get("api_url", "http://127.0.0.1:8000").rstrip("/")
if "/api/v1" in API_BASE_URL:
    API_BASE_URL = API_BASE_URL.split("/api/v1")[0]
elif "/predict" in API_BASE_URL:
    API_BASE_URL = API_BASE_URL.split("/predict")[0]

CLASS_NAMES = [
    "CORRECT", "SYNTAX_ERROR", "UNKNOWN_TABLE", "UNKNOWN_COLUMN",
    "DATATYPE_MISMATCH", "DUPLICATE_ALIAS", "PERMISSION_DENIED", "SEMANTIC_ERROR"
]

# Default Schema Catalogs
DEFAULT_SCHEMAS = {
    "University DB Schema": {
        "students": {
            "columns": {"id": "INTEGER", "name": "VARCHAR", "major": "VARCHAR", "gpa": "REAL", "advisor_id": "INTEGER"},
            "primary_keys": ["id"],
            "foreign_keys": []
        },
        "courses": {
            "columns": {"id": "INTEGER", "title": "VARCHAR", "credits": "INTEGER", "department": "VARCHAR"},
            "primary_keys": ["id"],
            "foreign_keys": []
        },
        "enrollments": {
            "columns": {"student_id": "INTEGER", "course_id": "INTEGER", "semester": "VARCHAR", "grade": "VARCHAR"},
            "primary_keys": ["student_id", "course_id"],
            "foreign_keys": [
                {"column": "student_id", "target_table": "students", "target_column": "id"},
                {"column": "course_id", "target_table": "courses", "target_column": "id"}
            ]
        }
    },
    "Company DB Schema": {
        "employees": {
            "columns": {"id": "INTEGER", "name": "VARCHAR", "role": "VARCHAR", "salary": "REAL", "dept_id": "INTEGER", "manager_id": "INTEGER"},
            "primary_keys": ["id"],
            "foreign_keys": []
        },
        "departments": {
            "columns": {"id": "INTEGER", "name": "VARCHAR", "location": "VARCHAR", "budget": "REAL"},
            "primary_keys": ["id"],
            "foreign_keys": []
        },
        "works_on": {
            "columns": {"emp_id": "INTEGER", "proj_id": "INTEGER", "hours": "REAL"},
            "primary_keys": ["emp_id", "proj_id"],
            "foreign_keys": [
                {"column": "emp_id", "target_table": "employees", "target_column": "id"}
            ]
        }
    },
    "Custom Schema (JSON)": {}
}

# Session State Initialization
if "history" not in st.session_state:
    st.session_state["history"] = []
if "sql_input" not in st.session_state:
    st.session_state["sql_input"] = ""
if "parsed_live_schema" not in st.session_state:
    st.session_state["parsed_live_schema"] = None

def add_to_history(query: str, error_class: str, confidence: float):
    limit = CONFIG["streamlit"].get("analytics", {}).get("history_limit", 10)
    history = st.session_state["history"]
    if not history or history[0]["query"] != query:
        history.insert(0, {"query": query, "class": error_class, "confidence": confidence})
    if len(history) > limit:
        history.pop()
    st.session_state["history"] = history

# Custom Token Highlighter Function
def render_token_highlights(tokens: List[str], attributions: List[str]) -> str:
    html_elements = []
    max_attr = max([abs(x) for x in attributions]) if attributions else 1.0
    if max_attr == 0:
        max_attr = 1.0
        
    for t, attr in zip(tokens, attributions):
        token_str = t.replace("Ġ", " ").replace("<s>", "").replace("</s>", "")
        if not token_str:
            continue
            
        weight = abs(attr) / max_attr
        alpha = min(0.65, max(0.08, weight * 0.5))
        
        if attr >= 0:
            bg_color = f"rgba(43, 140, 190, {alpha})"
            border = "rgba(43, 140, 190, 0.4)"
        else:
            bg_color = f"rgba(222, 45, 38, {alpha})"
            border = "rgba(222, 45, 38, 0.4)"
            
        html_elements.append(
            f'<span style="background-color: {bg_color}; border: 1px solid {border}; border-radius: 3px; padding: 2px 4px; margin: 2px; display: inline-block; font-family: monospace; color: #f8fafc;">'
            f'{token_str}'
            f'</span>'
        )
        
    return '<div style="background-color: #1e293b; border-radius: 8px; padding: 12px; line-height: 1.8; border: 1px solid #334155;">' + "".join(html_elements) + '</div>'

# Main App Title Layout
st.markdown('<div class="main-header">🛡️ Intelligent SQL Diagnostics, Auto-Repair & NL2SQL Suite</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Clean Architecture | Transformer Feature Attributions | Schema Parser | Rule-Based Repairs | Local Text-to-SQL</div>', unsafe_allow_html=True)

# Sidebar Configuration
sidebar = st.sidebar
sidebar.header("⚙️ System Control Center")

# API Health Status Check
server_connected = False
try:
    health_res = requests.get(f"{API_BASE_URL}/health", timeout=3)
    if health_res.status_code == 200:
        h_data = health_res.json()
        device_flag = h_data.get("device", "cpu").upper()
        sidebar.success(f"API Server: Online ({device_flag})")
        server_connected = True
    else:
        sidebar.error("API Server: Health Check Error")
except Exception:
    sidebar.error("API Server: Disconnected (Offline)")

# Active Database Schema Catalog Selection
sidebar.subheader("🗄️ Active Database Schema")

schema_options = list(DEFAULT_SCHEMAS.keys())
if st.session_state["parsed_live_schema"]:
    schema_options.insert(0, "Live Parsed DB Schema")

schema_sel = sidebar.selectbox("Choose database schema:", schema_options)

if schema_sel == "Live Parsed DB Schema" and st.session_state["parsed_live_schema"]:
    active_schema = st.session_state["parsed_live_schema"]
    sidebar.info("Using schema extracted via Database Schema Parser.")
elif schema_sel == "Custom Schema (JSON)":
    schema_json_input = sidebar.text_area(
        "Paste custom database schema JSON:",
        value='{\n  "users": {\n    "columns": {\n      "id": "INTEGER",\n      "name": "VARCHAR"\n    }\n  }\n}',
        height=150
    )
    try:
        active_schema = json.loads(schema_json_input)
    except Exception:
        sidebar.warning("Invalid JSON format. Schema context is empty.")
        active_schema = {}
else:
    active_schema = DEFAULT_SCHEMAS.get(schema_sel, {})

# Display Table Structure Preview
if active_schema:
    tables_summary = []
    for t, val in active_schema.items():
        cols = ", ".join([f"{k} ({v})" for k, v in val.get("columns", {}).items()])
        tables_summary.append({"Table": t, "Columns": cols})
    sidebar.dataframe(pd.DataFrame(tables_summary), hide_index=True)

# Query Execution History Panel
sidebar.subheader("⏳ Query History")
if st.session_state["history"]:
    for hist_idx, item in enumerate(st.session_state["history"]):
        hist_label = f"Q{hist_idx+1}: {item['query'][:18]}... ({item['class']})"
        if sidebar.button(hist_label, key=f"hist_{hist_idx}"):
            st.session_state["sql_input"] = item["query"]
            st.rerun()
else:
    sidebar.caption("No queries run in this session yet.")

# Main Navigation Tabs: 5 Full Service Suites
tab_single, tab_nl2sql, tab_batch, tab_schema, tab_metrics = st.tabs([
    "🔍 Analyze & Repair", 
    "✍️ Natural Language to SQL", 
    "📂 Batch & File Processing", 
    "🗄️ Database Schema Parser", 
    "📊 Telemetry & Metrics"
])

# ----------------------------------------------------
# TAB 1: Single Query Classification, Repair & XAI
# ----------------------------------------------------
with tab_single:
    col_input, col_output = st.columns([1, 1])
    
    with col_input:
        st.subheader("📝 SQL Query Input")
        
        uploaded_sql = st.file_uploader("Load SQL statement file (.sql)", type=["sql"])
        if uploaded_sql is not None:
            st.session_state["sql_input"] = uploaded_sql.read().decode("utf-8")
            
        sql_query_input = st.text_area(
            "Enter SQL query string to evaluate:",
            value=st.session_state["sql_input"],
            placeholder="SELECT name FROM students JOIN enrollments...",
            height=160,
            key="query_text_area"
        )
        
        analyze_btn = st.button("🚀 Analyze & Repair Query", type="primary")
        
    with col_output:
        st.subheader("💡 Diagnostic & Auto-Repair Output")
        if analyze_btn and sql_query_input.strip():
            with st.spinner("Processing classifier prediction, attributions & repair routing..."):
                predict_payload = {
                    "sql_query": sql_query_input,
                    "database_schema": active_schema,
                    "explain": True
                }
                
                try:
                    res_predict = requests.post(f"{API_BASE_URL}/predict", json=predict_payload, timeout=12)
                    if res_predict.status_code == 200:
                        pred_data = res_predict.json()
                        pred_class = pred_data["predicted_class"]
                        confidence = pred_data["confidence"]
                        latency_ms = pred_data["inference_time_ms"]
                        
                        add_to_history(sql_query_input, pred_class, confidence)
                        
                        if pred_class == "CORRECT":
                            st.success(f"Category: **{pred_class}** (Confidence: {confidence*100:.1f}% | Latency: {latency_ms:.2f}ms)")
                        else:
                            st.error(f"Category: **{pred_class}** (Confidence: {confidence*100:.1f}% | Latency: {latency_ms:.2f}ms)")
                            
                        st.progress(confidence, text="Classifier Confidence Meter")
                        
                        # Probabilities distribution chart
                        probs_df = pd.DataFrame([
                            {"Class": item["class_name"], "Probability": item["probability"]}
                            for item in pred_data["probabilities"]
                        ])
                        
                        with st.expander("📊 View All Class Probability Distributions"):
                            st.bar_chart(probs_df.set_index("Class"))
                            
                        # Repair routing
                        class_index = CLASS_NAMES.index(pred_class) if pred_class in CLASS_NAMES else 0
                        repair_payload = {
                            "sql_query": sql_query_input,
                            "predicted_class": class_index,
                            "database_schema": active_schema
                        }
                        
                        res_repair = requests.post(f"{API_BASE_URL}/repair", json=repair_payload, timeout=6)
                        if res_repair.status_code == 200:
                            rep_data = res_repair.json()
                            
                            st.markdown("### 🔧 Suggested Repair Engine Action")
                            st.write(f"**Diagnosis Explanation**: {rep_data['explanation']}")
                            st.write(f"**Recommended Action**: {rep_data['suggested_correction']}")
                            
                            if rep_data.get("corrected_query"):
                                st.markdown("**Auto-Corrected SQL Query**:")
                                st.code(rep_data["corrected_query"], language="sql")
                                
                            # XAI Token Attributions
                            xai_data = pred_data.get("explanation")
                            if xai_data and "tokens" in xai_data and "attributions" in xai_data:
                                st.markdown("### 🧬 Token Feature Attributions")
                                st.markdown(
                                    "Attribution weights relative to predicted category "
                                    "(<span style='color: #2b8cbe; font-weight: bold;'>teal</span> increases prediction, "
                                    "<span style='color: #de2d26; font-weight: bold;'>red</span> decreases it):",
                                    unsafe_allow_html=True
                                )
                                highlight_html = render_token_highlights(xai_data["tokens"], xai_data["attributions"])
                                st.markdown(highlight_html, unsafe_allow_html=True)
                                
                                if "attention_map" in xai_data and xai_data["attention_map"]:
                                    st.markdown("### 📊 Self-Attention Heatmap Matrix")
                                    fig, ax = plt.subplots(figsize=(7, 5))
                                    tokens = [t.replace("Ġ", " ").encode('ascii', errors='replace').decode('ascii') for t in xai_data["tokens"]]
                                    sns.heatmap(
                                        xai_data["attention_map"],
                                        xticklabels=tokens,
                                        yticklabels=tokens,
                                        cmap="viridis",
                                        ax=ax,
                                        cbar=False
                                    )
                                    plt.xticks(rotation=45, ha="right", fontsize=8)
                                    plt.yticks(fontsize=8)
                                    plt.title("Attention Heatmap Matrix", fontsize=10, fontweight="bold")
                                    plt.tight_layout()
                                    st.pyplot(fig)
                                    plt.close()
                                    
                                # Report Download
                                st.markdown("### 📑 Download Report")
                                r_content = f"# SQL Error Classification & Repair Report\n\n"
                                r_content += f"- **Target Query**: `{sql_query_input}`\n"
                                r_content += f"- **Classification**: `{pred_class}` (Confidence: {confidence*100:.1f}%)\n"
                                r_content += f"- **Explanation**: {rep_data['explanation']}\n"
                                r_content += f"- **Correction**: {rep_data['suggested_correction']}\n"
                                if rep_data.get("corrected_query"):
                                    r_content += f"- **Corrected SQL**: `{rep_data['corrected_query']}`\n"
                                    
                                st.download_button(
                                    label="📥 Download Diagnostic Report (Markdown)",
                                    data=r_content,
                                    file_name="sql_diagnostic_report.md",
                                    mime="text/markdown"
                                )
                        else:
                            st.warning("Could not contact auto-repair endpoint.")
                    else:
                        st.error(f"Classification request failed with status {res_predict.status_code}")
                except Exception as e:
                    st.error(f"API Communication Error: {e}")
        else:
            st.info("Enter a SQL statement and click 'Analyze & Repair Query' to run the classification model.")

# ----------------------------------------------------
# TAB 2: Natural Language to SQL Generation & Pipeline Validation
# ----------------------------------------------------
with tab_nl2sql:
    st.subheader("✍️ Text-to-SQL Translation & Automated Pipeline Validation")
    st.write(
        "Convert plain English questions into context-aware SQL queries using a local T5 model. "
        "The generated query is automatically validated by our classifier and repaired if errors are found."
    )
    
    nl_question = st.text_input(
        "Type your question in plain English:",
        placeholder="Show department names where average salary is greater than 60000"
    )
    
    conf_thresh = st.slider(
        "Confidence Threshold Warning Sensitivity:",
        min_value=0.0,
        max_value=1.0,
        value=0.5,
        step=0.05
    )
    
    generate_btn = st.button("🪄 Translate & Validate Query", type="primary")
    
    if generate_btn and nl_question.strip():
        with st.spinner("Generating SQL query via T5, validating classifier, and checking auto-repair..."):
            nl2sql_payload = {
                "question": nl_question,
                "database_schema": active_schema,
                "confidence_threshold": conf_thresh
            }
            
            try:
                res_nl2sql = requests.post(f"{API_BASE_URL}/generate_sql", json=nl2sql_payload, timeout=25)
                if res_nl2sql.status_code == 200:
                    gen_data = res_nl2sql.json()
                    
                    generated_sql = gen_data["generated_sql"]
                    confidence = gen_data["confidence"]
                    validation = gen_data["validation"]
                    repaired_sql = gen_data["repaired_sql"]
                    explanation = gen_data["explanation"]
                    warning = gen_data.get("warning")
                    alternatives = gen_data.get("alternatives")
                    latency = gen_data["inference_time_ms"]
                    
                    st.markdown(f"### 🚀 Generated SQL Query (Latency: {latency:.2f}ms)")
                    st.code(generated_sql, language="sql")
                    
                    st.markdown(f"**Generation Confidence**: {confidence*100:.1f}%")
                    st.progress(confidence)
                    
                    if warning:
                        st.warning(warning)
                        
                    if alternatives:
                        st.markdown("**Top Alternative Candidate Queries**:")
                        for idx, alt in enumerate(alternatives):
                            st.write(f"{idx+1}. `{alt}`")
                            
                    st.markdown("---")
                    st.markdown("### 🛡️ Automated Validation & Repair Pipeline")
                    
                    val_class = validation["predicted_class"]
                    val_conf = validation["confidence"]
                    is_error = validation["is_error"]
                    
                    if not is_error:
                        st.success(f"🟢 **Valid Query**: Classifier verified query status as **CORRECT** (Confidence: {val_conf*100:.1f}%).")
                    else:
                        st.error(f"🔴 **Error Detected**: Classifier predicted **{val_class}** (Confidence: {val_conf*100:.1f}%).")
                        
                        if repaired_sql:
                            st.markdown("### 🔧 Auto-Repaired Query:")
                            st.code(repaired_sql, language="sql")
                            
                            if explanation:
                                st.write(f"**Diagnosis Explanation**: {explanation.get('explanation')}")
                                st.write(f"**Suggested Action**: {explanation.get('suggested_correction')}")
                        else:
                            st.info("No auto-repair options could be resolved for this category.")
                else:
                    st.error(f"Text-to-SQL generation failed with status code {res_nl2sql.status_code}")
            except Exception as e:
                st.error(f"API Communication Error: {e}")

# ----------------------------------------------------
# TAB 3: Batch Processing (CSV Upload & Array Endpoint)
# ----------------------------------------------------
with tab_batch:
    st.subheader("📂 Batch Processing & Multi-Query Diagnostics")
    
    sub_csv, sub_array = st.tabs(["📄 CSV File Upload (/upload)", "📋 Multi-Query Array (/batch)"])
    
    with sub_csv:
        st.write(
            "Upload a CSV file containing multiple SQL query rows. "
            "Must contain a `sql_query` or `query` column, and optional `database_schema` column."
        )
        
        uploaded_file = st.file_uploader("Choose a CSV file:", type=["csv"], key="batch_csv_file")
        
        if uploaded_file is not None:
            with st.spinner("Running batch classification and auto-repairs on uploaded CSV..."):
                files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "text/csv")}
                try:
                    res_upload = requests.post(f"{API_BASE_URL}/upload", files=files, timeout=60)
                    if res_upload.status_code == 200:
                        records = res_upload.json()
                        
                        parsed_records = []
                        for r in records:
                            q = r.get("query")
                            pred = r.get("classification", {}).get("predicted_class", "unknown")
                            conf = r.get("classification", {}).get("confidence", 0.0)
                            suggest = r.get("repair", {}).get("suggested_correction", "None")
                            fixed = r.get("repair", {}).get("corrected_query", "")
                            
                            parsed_records.append({
                                "SQL Query": q,
                                "Detected Error Category": pred,
                                "Confidence": f"{conf*100:.1f}%",
                                "Suggested Correction": suggest,
                                "Repaired Query": fixed
                            })
                            
                        res_df = pd.DataFrame(parsed_records)
                        st.success(f"Successfully processed {len(res_df)} query rows!")
                        st.dataframe(res_df, use_container_width=True)
                        
                        output_csv = res_df.to_csv(index=False)
                        st.download_button(
                            label="📥 Download Corrected Batch CSV",
                            data=output_csv,
                            file_name="sql_batch_repaired_results.csv",
                            mime="text/csv"
                        )
                    else:
                        st.error(f"Batch CSV upload failed with status code {res_upload.status_code}")
                except Exception as e:
                    st.error(f"Error processing CSV batch upload: {e}")
                    
    with sub_array:
        st.write("Paste multiple SQL queries below (one per line) to process them sequentially via the `/batch` endpoint.")
        
        batch_text_input = st.text_area(
            "SQL Statements List:",
            value="SELECT name salary FROM employees\nSELECT * FROM non_existent_table\nSELECT name FROM employees WHERE salary > 50000",
            height=150
        )
        
        run_repair_check = st.checkbox("Run Auto-Repair for Detected Errors", value=True)
        run_batch_btn = st.button("🚀 Process Batch Statements", type="primary")
        
        if run_batch_btn and batch_text_input.strip():
            queries_list = [line.strip() for line in batch_text_input.strip().split("\n") if line.strip()]
            
            batch_payload = {
                "queries": queries_list,
                "database_schemas": [active_schema] * len(queries_list),
                "run_repair": run_repair_check
            }
            
            with st.spinner(f"Batch processing {len(queries_list)} SQL statements..."):
                try:
                    res_batch = requests.post(f"{API_BASE_URL}/batch", json=batch_payload, timeout=30)
                    if res_batch.status_code == 200:
                        batch_res_data = res_batch.json()
                        results_array = batch_res_data.get("results", [])
                        
                        table_rows = []
                        for item in results_array:
                            q_text = item.get("query")
                            c_info = item.get("classification", {})
                            p_class = c_info.get("predicted_class", "N/A")
                            p_conf = c_info.get("confidence", 0.0)
                            
                            r_info = item.get("repair", {})
                            c_query = r_info.get("corrected_query", "N/A") if r_info else "N/A"
                            s_action = r_info.get("suggested_correction", "N/A") if r_info else "N/A"
                            
                            table_rows.append({
                                "Query": q_text,
                                "Predicted Class": p_class,
                                "Confidence": f"{p_conf*100:.1f}%",
                                "Repaired Query": c_query,
                                "Suggested Action": s_action
                            })
                            
                        st.success(f"Processed {len(table_rows)} queries via `/batch` endpoint.")
                        st.dataframe(pd.DataFrame(table_rows), use_container_width=True)
                    else:
                        st.error(f"Batch API returned status code {res_batch.status_code}")
                except Exception as e:
                    st.error(f"Batch Processing Error: {e}")

# ----------------------------------------------------
# TAB 4: Database Schema Extraction & Parsing Service
# ----------------------------------------------------
with tab_schema:
    st.subheader("🗄️ Database Schema Extraction Service")
    st.write(
        "Directly extract tables, columns, primary keys, and foreign keys from live **SQLite**, "
        "**PostgreSQL**, or **MySQL** databases, and convert them to internal JSON catalogs or SQL DDL."
    )
    
    db_type = st.radio("Select Target Database Type:", ["SQLite (.db File)", "PostgreSQL Connection", "MySQL Connection"], horizontal=True)
    
    if db_type == "SQLite (.db File)":
        sqlite_file = st.file_uploader("Upload SQLite database file (.db / .sqlite):", type=["db", "sqlite", "sqlite3"])
        
        if sqlite_file is not None:
            if st.button("⚡ Extract SQLite Schema", type="primary"):
                with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
                    tmp.write(sqlite_file.getvalue())
                    tmp_path = tmp.name
                    
                try:
                    parsed_schema = DatabaseSchemaParser.parse_sqlite(tmp_path)
                    st.session_state["parsed_live_schema"] = parsed_schema
                    
                    st.success(f"Successfully extracted schema! Found {len(parsed_schema)} table(s).")
                    
                    col_json, col_ddl = st.columns([1, 1])
                    with col_json:
                        st.markdown("### 📋 Internal Schema Catalog (JSON)")
                        st.json(parsed_schema)
                        
                    with col_ddl:
                        st.markdown("### 📜 Standard DDL Format")
                        ddl_text = DatabaseSchemaParser.to_ddl(parsed_schema)
                        st.code(ddl_text, language="sql")
                        
                    st.info("Tip: 'Live Parsed DB Schema' is now active in the sidebar for classification & NL2SQL generation!")
                except Exception as e:
                    st.error(f"Failed to parse SQLite schema: {e}")
                    
    elif db_type == "PostgreSQL Connection":
        pg_conn_str = st.text_input("PostgreSQL Connection String:", value="dbname=test user=postgres password=secret host=localhost port=5432")
        if st.button("⚡ Connect & Extract PostgreSQL Schema", type="primary"):
            try:
                parsed_schema = DatabaseSchemaParser.parse_postgresql(pg_conn_str)
                st.session_state["parsed_live_schema"] = parsed_schema
                st.success(f"Successfully extracted PostgreSQL schema! Found {len(parsed_schema)} table(s).")
                st.json(parsed_schema)
            except Exception as e:
                st.error(f"PostgreSQL connection failed: {e}")
                
    elif db_type == "MySQL Connection":
        my_conn_str = st.text_input("MySQL Connection String:", value="host=localhost user=root password=secret database=test")
        if st.button("⚡ Connect & Extract MySQL Schema", type="primary"):
            try:
                parsed_schema = DatabaseSchemaParser.parse_mysql(my_conn_str)
                st.session_state["parsed_live_schema"] = parsed_schema
                st.success(f"Successfully extracted MySQL schema! Found {len(parsed_schema)} table(s).")
                st.json(parsed_schema)
            except Exception as e:
                st.error(f"MySQL connection failed: {e}")

# ----------------------------------------------------
# TAB 5: Operational Telemetry & Health Dashboard
# ----------------------------------------------------
with tab_metrics:
    st.subheader("📊 API Operational Telemetry & System Health")
    
    if st.button("🔄 Refresh Telemetry Metrics"):
        st.rerun()
        
    try:
        res_health = requests.get(f"{API_BASE_URL}/health", timeout=3)
        res_metrics = requests.get(f"{API_BASE_URL}/metrics", timeout=3)
        
        if res_health.status_code == 200 and res_metrics.status_code == 200:
            h_data = res_health.json()
            m_data = res_metrics.json()
            
            # Key Metrics Cards
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("API Status", h_data.get("status", "N/A").upper())
            with col2:
                st.metric("Total Predictions", m_data.get("total_predictions", 0))
            with col3:
                st.metric("Total Auto-Repairs", m_data.get("total_repairs", 0))
            with col4:
                st.metric("Avg Latency", f"{m_data.get('avg_inference_time_ms', 0.0):.2f} ms")
                
            st.markdown("---")
            
            col_chart, col_details = st.columns([1, 1])
            
            with col_chart:
                st.markdown("### 📈 Error Category Counts Breakdown")
                counts = m_data.get("error_class_counts", {})
                if counts:
                    counts_df = pd.DataFrame(list(counts.items()), columns=["Category", "Count"])
                    st.bar_chart(counts_df.set_index("Category"))
                else:
                    st.info("No prediction telemetry logged yet.")
                    
            with col_details:
                st.markdown("### 🖥️ Hardware & Execution Environment")
                st.write(f"- **Hardware Execution Target**: `{h_data.get('device', 'N/A').upper()}`")
                st.write(f"- **ML Transformer Model Loaded**: `{h_data.get('model_loaded', False)}`")
                st.write(f"- **Backend Target Domain**: `{API_BASE_URL}`")
                st.write(f"- **Active Config Classes Count**: `8 Categories`")
        else:
            st.error("Failed to retrieve telemetry metrics from API backend.")
    except Exception as e:
        st.error(f"Error fetching API telemetry logs: {e}")
