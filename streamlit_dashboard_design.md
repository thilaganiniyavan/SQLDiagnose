# Streamlit Dashboard UI Design Plan

This document outlines the user interface (UI) and user experience (UX) layout plan for the **SQL Diagnostic Hub**, a professional, dark-themed Streamlit dashboard designed to analyze SQL queries, categorize errors, visualize transformer attention states, and suggest fixes.

---

## 1. Dashboard Layout Wireframe

```text
+---------------------------------------------------------------------------------------------------+
|  [SQL DIAGNOSTIC HUB] - Multi-Class SQL Error Analyzer                                            |
+---------------------------------------------------------------------------------------------------+
|  SIDEBAR                   |  MAIN PANEL                                                          |
|                            |                                                                      |
|  [Select Schema Catalog]   |  [ Workspace Area ] ───────────────────────────────────────────────┐  |
|  ( ) PostgreSQL (Default)  |  |                                                                 |  |
|  ( ) SQLite E-Commerce     |  |  SELECT name, bio FROM users JOIN profiles ON users.id =        |  |
|                            |  |  [ Analyze Query ] [ Clear ]                                    |  |
|  [Input Source]            |  └─────────────────────────────────────────────────────────────────┘  |
|  (*) Text Editor           |                                                                      |
|  ( ) File Upload (.sql)    |  [ Diagnostic Output ] ────────────────────────────────────────────┐  |
|                            |  |  Status: [ ERROR: MISSING_JOIN_CONDITION ] (Confidence: 89.2%)    |  |
|  [Diagnostics History]     |  |                                                                 |  |
|  - SELECT age FROM... (X)  |  |  *Highlighted Tokens:*                                          |  |
|  - SELECT * FROM...   (O)  |  |  SELECT name, bio FROM users JOIN profiles ON users.id = [ERR]  |  |
|                            |  |                                                                 |  |
|  [Threshold Options]       |  |  *Suggested Fix:*                                               |  |
|  Min Confidence: [15% ]    |  |  SELECT name, bio FROM users JOIN profiles ON users.id =        |  |
|                            |  |  profiles.user_id                                               |  |
|  [Export Options]          |  └─────────────────────────────────────────────────────────────────┘  |
|  [ Export PDF Report ]     |                                                                      |
|  [ Export Markdown ]       |  [ Model Probability Breakdown ] [ Attention Visualization ] ──────┐  |
|                            |  |  - Correct:       [█░░░░░] 2.1%  | Token-to-Token Attention Map |  |
|                            |  |  - Missing Join:  [█████] 89.2%  | (Interactive Heatmap Grid)   |  |
|                            |  |  - Unknown Table: [░░░░░░] 0.5%  |                              |  |
|                            |  └─────────────────────────────────────────────────────────────────┘  |
+---------------------------------------------------------------------------------------------------+
```

---

## 2. Dashboard Component Specifications

### A. Sidebar Navigation & Control Panel
-   **Header**: Standard high-resolution logo and title: `SQL Diagnostic Hub v1.0`.
-   **Database Schema Selector**: Dropdown selection loading serialized YAML schemas (e.g. `Spider - Classic Cars`, `BIRD - Financial DB`). Displays a table with table names and data types when a schema is selected.
-   **Input Mode Controller**: Radio toggle supporting two formats:
    1.  **Text Editor Mode**: Active coding container area.
    2.  **File Upload Mode**: Triggers a drag-and-drop container (`st.file_uploader`) accepting `.sql` and `.txt` files up to 200KB.
-   **Threshold Slider**: Configures the minimum confidence threshold to display error categories (default 15%), filtering out low-confidence predictions.
-   **Analysis History Tracker**: Uses `st.expander` to list the last 10 processed queries. Clicking a history item restores that query's text and execution results.
-   **Export Controller**: Buttons to trigger background report builders compiling predictions, metrics, and figures into downloadable formats:
    -   `[ Export PDF Report ]` (using ReportLab).
    -   `[ Export Markdown ]` (raw text format).

---

### B. Main Panel Component Blocks

#### 1. Workspace Input Area
-   **Description**: The direct interactive input panel.
-   **Details**:
    -   Uses `st.text_area` with custom height settings, styled with monospace font layout parameters.
    -   Displays two control CTAs aligned horizontally: `[ Analyze Query ]` (primary color theme) and `[ Clear Editor ]`.

#### 2. Diagnostic Summary & Token Highlighting
-   **Description**: Displays model predictions and structural differences.
-   **Details**:
    -   **Classification Banner**: Green banner (`st.success`) if predicted class is `CORRECT`. Red banner (`st.error`) if model outputs a class error, displaying predicted error category and confidence score percentage.
    -   **Token Highlighting Container**: Custom HTML container utilizing Streamlit’s HTML component (`st.components.v1.html`). Syntactically incorrect tokens (e.g., mismatched brackets or columns) are highlighted with red backdrops and warning tooltips.
    -   **Suggested Fix Block**: Displays side-by-side SQL panels comparing original and corrected code blocks:
        -   Uses a code-diff display format showing additions (`+`) in green and deletions (`-`) in red.

#### 3. Model Probabilities & Explainability
-   **Description**: Explains the model's decision making process.
-   **Details**:
    -   **Class Probabilities Plot**: An interactive horizontal bar chart (using `st.plotly_chart` or native `st.bar_chart`) showing confidence scores for all 8 categories.
    -   **Attention Map Visualization**: Renders an interactive attention heatmap grid (using Plotly Heatmap). Shows self-attention scores between query tokens (X-axis) and database schema tokens (Y-axis), demonstrating how the model identified missing columns or table syntax issues.

---

## 3. Dark Theme & Appearance Styling

To enforce a professional appearance, the interface configures the following theme settings in `.streamlit/config.toml`:

```toml
[theme]
primaryColor = "#00FFFF"          # Cyan highlights for active components
backgroundColor = "#0F111A"       # Deep dark blue-black base
secondaryBackgroundColor = "#1E2235" # Subtle slate-blue container panels
textColor = "#FFFFFF"             # Crisp white readability text
font = "monospace"                # Technical code-oriented layout font
```
-   **Interactive Elements**: Uses hover transitions (cyan border highlights) on code entry boxes and button CTAs.
-   **Status Badges**: Maps status badges to specific colors (e.g., `EASY` $\to$ Green, `MEDIUM` $\to$ Orange, `HARD` $\to$ Red).
-   **Padding & Alignments**: Standardizes on clean column-grids (`st.columns`) and minimal vertical spacing to maximize information density.
