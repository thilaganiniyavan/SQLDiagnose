# app.py
# Clean Architecture: Frameworks & Drivers
# Streamlit Interface for interacting with SQL error classification and repair models.

import streamlit as st
import requests
import json
import yaml
import io
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
from pathlib import Path
from typing import Dict, Any, List

# Set Page Config
st.set_page_config(
    page_title="SQL Error Classifier Dashboard",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Load Configuration
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
# Clean up target route to get the base domain (e.g. http://localhost:8000/api/v1/classify -> http://localhost:8000)
if "/api/v1" in API_BASE_URL:
    API_BASE_URL = API_BASE_URL.split("/api/v1")[0]
elif "/predict" in API_BASE_URL:
    API_BASE_URL = API_BASE_URL.split("/predict")[0]

# Setup Default Schema Catalogs
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
    "Custom Schema (Empty)": {}
}

# Session State Initialization
if "history" not in st.session_state:
    st.session_state["history"] = []
if "sql_input" not in st.session_state:
    st.session_state["sql_input"] = ""

def add_to_history(query: str, error_class: str, confidence: float):
    limit = CONFIG["streamlit"].get("analytics", {}).get("history_limit", 10)
    history = st.session_state["history"]
    # Prevent duplicate sequential items
    if not history or history[0]["query"] != query:
        history.insert(0, {"query": query, "class": error_class, "confidence": confidence})
    if len(history) > limit:
        history.pop()
    st.session_state["history"] = history

# Custom Token Highlighter Function
def render_token_highlights(tokens: List[str], attributions: List[str]) -> str:
    """
    Renders SQL string with colored spans indicating attribution weights.
    Positive attributions are highlighted in transparent teal/blue.
    Negative attributions are highlighted in transparent red/orange.
    """
    html_elements = []
    
    # Simple normalization of attributions for visibility scaling
    max_attr = max([abs(x) for x in attributions]) if attributions else 1.0
    if max_attr == 0:
        max_attr = 1.0
        
    for t, attr in zip(tokens, attributions):
        # Clean BPE tokenizer spacing artifacts for HTML presentation
        token_str = t.replace("Ġ", " ").replace("<s>", "").replace("</s>", "")
        if not token_str:
            continue
            
        weight = abs(attr) / max_attr
        # Cap alpha transparency range
        alpha = min(0.65, max(0.08, weight * 0.5))
        
        if attr >= 0:
            # Positive impact towards class prediction (Teal)
            bg_color = f"rgba(43, 140, 190, {alpha})"
            border = "rgba(43, 140, 190, 0.4)"
        else:
            # Negative impact against class prediction (Red)
            bg_color = f"rgba(222, 45, 38, {alpha})"
            border = "rgba(222, 45, 38, 0.4)"
            
        html_elements.append(
            f'<span style="background-color: {bg_color}; border: 1px solid {border}; border-radius: 3px; padding: 2px 4px; margin: 2px; display: inline-block; font-family: monospace; color: #f8fafc;">'
            f'{token_str}'
            f'</span>'
        )
        
    return '<div style="background-color: #1e293b; border-radius: 8px; padding: 12px; line-height: 1.8; border: 1px solid #334155;">' + "".join(html_elements) + '</div>'

# Main App Layout
st.title("🛡️ SQL Error Diagnostics & Auto-Repair Dashboard")
st.caption("Clean Architecture | Transformer Feature Attribution | Rule-Based Active Catalog Repairs")

# Columns layout: Sidebar and Main panels
sidebar = st.sidebar
sidebar.header("⚙️ Configuration Catalog")

# 1. API Health status check
try:
    health_res = requests.get(f"{API_BASE_URL}/health", timeout=3)
    if health_res.status_code == 200:
        h_data = health_res.json()
        device_flag = h_data.get("device", "cpu").upper()
        sidebar.success(f"Backend Server: Connected ({device_flag})")
    else:
        sidebar.error("Backend Server: Error Response")
except Exception:
    sidebar.error("Backend Server: Disconnected")

# 2. Database Schema Catalog Selection
sidebar.subheader("🗄️ Active Database Schema")
schema_sel = sidebar.selectbox("Choose database schema template:", list(DEFAULT_SCHEMAS.keys()))

schema_json_input = ""
if schema_sel == "Custom Schema (Empty)":
    schema_json_input = sidebar.text_area(
        "Paste custom database schema JSON:",
        value='{\n  "users": {\n    "columns": {\n      "id": "INTEGER",\n      "name": "VARCHAR"\n    }\n  }\n}',
        height=150
    )
    try:
        active_schema = json.loads(schema_json_input)
    except Exception:
        sidebar.warning("Invalid JSON format. Schema matching is disabled.")
        active_schema = {}
else:
    active_schema = DEFAULT_SCHEMAS[schema_sel]
    # Display table structure
    if active_schema:
        tables_summary = []
        for t, val in active_schema.items():
            cols = ", ".join([f"{k} ({v})" for k, v in val["columns"].items()])
            tables_summary.append({"Table": t, "Columns": cols})
        sidebar.dataframe(pd.DataFrame(tables_summary), hide_index=True)

# 3. Query Execution History sidebar panel
sidebar.subheader("⏳ Query History")
if st.session_state["history"]:
    for hist_idx, item in enumerate(st.session_state["history"]):
        hist_label = f"Q{hist_idx+1}: {item['query'][:20]}... ({item['class']})"
        if sidebar.button(hist_label, key=f"hist_{hist_idx}"):
            st.session_state["sql_input"] = item["query"]
            st.rerun()
else:
    sidebar.caption("No queries run in this session yet.")

# Main Panel Interface Tabs
tab_single, tab_batch = st.tabs(["🔍 Analyze & Repair", "📂 Batch Upload Analysis"])

with tab_single:
    col_input, col_output = st.columns([1, 1])
    
    with col_input:
        st.subheader("📝 SQL Query Editor")
        
        # File uploader to load SQL file
        uploaded_sql = st.file_uploader("Load a SQL query file (.sql)", type=["sql"])
        if uploaded_sql is not None:
            st.session_state["sql_input"] = uploaded_sql.read().decode("utf-8")
            
        sql_query_input = st.text_area(
            "Enter SQL statement to diagnose:",
            value=st.session_state["sql_input"],
            placeholder="SELECT name FROM students JOIN enrollments...",
            height=150,
            key="query_text_area"
        )
        
        analyze_btn = st.button("🚀 Analyze & Repair SQL", type="primary")
        
    with col_output:
        st.subheader("💡 Diagnostic Diagnostics")
        if analyze_btn and sql_query_input.strip():
            with st.spinner("Executing model prediction & explainability attributions..."):
                # 1. POST Predict request
                predict_payload = {
                    "sql_query": sql_query_input,
                    "database_schema": active_schema,
                    "explain": True
                }
                
                try:
                    res_predict = requests.post(f"{API_BASE_URL}/predict", json=predict_payload, timeout=10)
                    if res_predict.status_code == 200:
                        pred_data = res_predict.json()
                        pred_class = pred_data["predicted_class"]
                        confidence = pred_data["confidence"]
                        
                        # Add to history
                        add_to_history(sql_query_input, pred_class, confidence)
                        
                        # Render category and confidence meter
                        if pred_class == "CORRECT":
                            st.success(f"Category: **{pred_class}** (Confidence: {confidence*100:.1f}%)")
                        else:
                            st.error(f"Category: **{pred_class}** (Confidence: {confidence*100:.1f}%)")
                            
                        st.progress(confidence, text="Confidence Level")
                        
                        # 2. POST Repair request
                        # Retrieve index mapping matching category
                        class_index = CLASS_NAMES = [
                            "CORRECT", "SYNTAX_ERROR", "UNKNOWN_TABLE", "UNKNOWN_COLUMN",
                            "DATATYPE_MISMATCH", "DUPLICATE_ALIAS", "PERMISSION_DENIED", "SEMANTIC_ERROR"
                        ].index(pred_class)
                        
                        repair_payload = {
                            "sql_query": sql_query_input,
                            "predicted_class": class_index,
                            "database_schema": active_schema
                        }
                        
                        res_repair = requests.post(f"{API_BASE_URL}/repair", json=repair_payload, timeout=5)
                        if res_repair.status_code == 200:
                            rep_data = res_repair.json()
                            
                            st.markdown("### 🔧 Suggested Repair Options")
                            st.write(f"**Explanation**: {rep_data['explanation']}")
                            st.write(f"**Suggested Correction**: {rep_data['suggested_correction']}")
                            
                            if rep_data.get("corrected_query"):
                                st.markdown("**Corrected SQL Query**:")
                                st.code(rep_data["corrected_query"], language="sql")
                                
                            # 3. Render Token Highlights
                            xai_data = pred_data.get("explanation")
                            if xai_data and "tokens" in xai_data and "attributions" in xai_data:
                                st.markdown("### 🧬 Token Feature Attributions")
                                st.markdown(
                                    "Highlighted using Integrated Gradients attributions relative to predicted error category "
                                    "(<span style='color: #2b8cbe; font-weight: bold;'>teal</span> helps prediction, "
                                    "<span style='color: #de2d26; font-weight: bold;'>red</span> runs against it):",
                                    unsafe_allow_html=True
                                )
                                highlight_html = render_token_highlights(xai_data["tokens"], xai_data["attributions"])
                                st.markdown(highlight_html, unsafe_allow_html=True)
                                
                                # Render Heatmap locally
                                st.markdown("### 📊 Attention Heatmap Plot")
                                fig, ax = plt.subplots(figsize=(8, 6))
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
                                plt.title("Attention Heatmap Matrix (Last Layer Mean)", fontsize=10, fontweight="bold")
                                plt.tight_layout()
                                st.pyplot(fig)
                                plt.close()
                                
                                # Render Report Download
                                st.markdown("### 📑 Download Diagnostic Report")
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
                            st.warning("Failed to connect to the repair engine.")
                    else:
                        st.error("Failed to compile model prediction.")
                except Exception as e:
                    st.error(f"Error communicating with API backend: {e}")
        else:
            st.info("Input a SQL statement and click 'Analyze & Repair SQL' to execute model diagnostics.")

with tab_batch:
    st.subheader("📂 Batch Process SQL Statements from CSV File")
    st.write(
        "Upload a CSV file containing multiple SQL statement rows. The CSV file must have a `sql_query` or `query` column, "
        "and an optional `database_schema` column."
    )
    
    uploaded_file = st.file_uploader("Choose a CSV file:", type=["csv"])
    
    if uploaded_file is not None:
        with st.spinner("Processing file upload and running batch corrections..."):
            # Post file upload
            files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "text/csv")}
            
            try:
                res_upload = requests.post(f"{API_BASE_URL}/upload", files=files, timeout=60)
                if res_upload.status_code == 200:
                    records = res_upload.json()
                    
                    # Compile results table for presentation
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
                    st.success(f"Successfully processed {len(res_df)} queries!")
                    st.dataframe(res_df, use_container_width=True)
                    
                    # Download repaired CSV option
                    output_csv = res_df.to_csv(index=False)
                    st.download_button(
                        label="📥 Download Corrected Batch CSV",
                        data=output_csv,
                        file_name="sql_batch_repaired_results.csv",
                        mime="text/csv"
                    )
                else:
                    st.error(f"Upload processing failed with status code {res_upload.status_code}")
            except Exception as e:
                st.error(f"Error sending batch upload request: {e}")
