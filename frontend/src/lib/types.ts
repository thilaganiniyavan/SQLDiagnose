// Wire types of the SQLDiagnose REST API (/api/v1). Keep in sync with deployment/api/schemas.py.

export type ErrorClass =
  | 'CORRECT'
  | 'SYNTAX_ERROR'
  | 'UNKNOWN_TABLE'
  | 'UNKNOWN_COLUMN'
  | 'DATATYPE_MISMATCH'
  | 'AMBIGUOUS_REFERENCE'
  | 'PERMISSION_DENIED'
  | 'SEMANTIC_ERROR'

export interface ForeignKey {
  column: string
  target_table: string
  target_column: string
}

export interface TableSchema {
  columns: Record<string, string>
  primary_keys?: string[]
  foreign_keys?: ForeignKey[]
}

export type DatabaseSchema = Record<string, TableSchema>

export interface AccessPolicy {
  restricted_tables: string[]
  restricted_columns: string[]
}

/** Schema selection sent with every query request. */
export interface SchemaContextBody {
  db_id?: string
  schema_id?: string
  database_schema?: DatabaseSchema
  access_policy?: AccessPolicy
}

export interface Issue {
  error_class: ErrorClass
  message: string
  token: string | null
  source: 'engine' | 'static' | 'policy' | string
}

export interface AnalysisResult {
  error_class: ErrorClass
  is_error: boolean
  issues: Issue[]
  engine_error: string | null
  schema_checked: boolean
}

export interface ModelPrediction {
  error_class: ErrorClass
  confidence: number
  probabilities: Record<string, number>
}

export interface TokenScore {
  token: string
  score: number
}

export interface Explanation {
  target_class?: ErrorClass
  method?: string
  query_tokens?: TokenScore[]
  schema_tokens?: TokenScore[]
  probability?: number
  error?: string
}

export interface Diagnosis {
  query: string
  is_error: boolean
  error_class: ErrorClass
  description: string
  confidence: number
  decided_by: 'analyzer' | 'model' | 'analyzer+model' | string
  analysis: AnalysisResult | null
  model: ModelPrediction | null
  notes: string[]
  explanation: Explanation | null
  latency_ms: number
}

export interface RepairStep {
  error_class: ErrorClass
  description: string
  before: string
  after: string
}

export interface RepairResult {
  original_query: string
  repaired_query: string | null
  success: boolean
  remaining_error: ErrorClass | null
  steps: RepairStep[]
  explanation: string
}

export interface AnalyzeResponse {
  diagnosis: Diagnosis
  repair: RepairResult | null
  latency_ms: number
  history_id: string | null
}

export interface BatchRow {
  query: string
  is_error: boolean
  error_class: ErrorClass
  confidence: number
  decided_by: string
  issues: string[]
  model_prediction: ErrorClass | null
  repaired_query?: string | null
  repair_success?: boolean
  repair_explanation?: string
}

export interface Candidate {
  sql: string
  confidence: number
  rank: number
  error_class: ErrorClass
  issues: string[]
}

export type NL2SQLStatus = 'valid' | 'valid_alternative' | 'repaired' | 'invalid' | 'no_candidate'

export interface NL2SQLResult {
  question: string
  sql: string | null
  status: NL2SQLStatus
  candidates: Candidate[]
  repair: RepairResult | null
  diagnosis: Omit<Diagnosis, 'description' | 'explanation' | 'latency_ms'> | null
  generator: string
  prompt_truncated: boolean
  generation_time_ms: number
  latency_ms: number
  history_id?: string
}

export interface Job<T> {
  id: string
  kind: string
  status: 'queued' | 'running' | 'done' | 'error' | 'cancelled'
  phase: 'loading_model' | 'generating' | null
  queue_position: number
  result: T | null
  error: string | null
  created_at: number
  started_at: number | null
  finished_at: number | null
  elapsed_s: number
  question?: string
}

export interface ExecuteResult {
  columns: string[]
  rows: unknown[][]
  row_count: number
  truncated: boolean
  elapsed_ms: number
}

export interface Health {
  status: string
  version: string
  model_loaded: boolean
  model: {
    path: string
    backbone: string
    labels: string[]
    validation?: { macro_f1?: number; accuracy?: number } | null
    parameters: number
  } | null
  generator_loaded: boolean
  generator: string | null
  generator_error: string | null
  example_databases: number
  executable_databases: number
  live_schema_enabled: boolean
  results_available: boolean
  workspace_enabled: boolean
}

export interface Metrics {
  uptime_s: number
  requests: Record<string, number>
  diagnoses: number
  repairs: number
  repairs_successful: number
  mean_diagnosis_latency_ms: number
  class_counts: Record<string, number>
}

export interface Label {
  id: number
  name: ErrorClass
  description: string
}

export interface ExampleDatabase {
  db_id: string
  tables: number
  columns: number
  executable: boolean
}

export interface ExampleSchemaDetail {
  db_id: string
  database_schema: DatabaseSchema
  ddl: string
  executable: boolean
}

export interface SavedSchemaSummary {
  id: string
  name: string
  source: 'json' | 'ddl' | 'sqlite' | 'live' | 'example'
  access_policy: AccessPolicy | null
  executable: boolean
  tables: number
  columns: number
  created_at: number
  updated_at: number
}

export interface SavedSchema extends SavedSchemaSummary {
  database_schema: DatabaseSchema
  ddl?: string
}

export type HistoryKind = 'analyze' | 'nl2sql' | 'batch'

export interface HistoryItem {
  id: string
  kind: HistoryKind
  title: string
  context: SchemaContextBody
  error_class: ErrorClass | null
  summary: Record<string, unknown>
  created_at: number
  has_result: boolean
  result?: unknown
}

export interface HistoryPage {
  total: number
  items: HistoryItem[]
}

export interface ClassifierMetrics {
  accuracy: number
  macro_precision: number
  macro_recall: number
  macro_f1: number
  macro_roc_auc?: number
  ece?: number
  per_class: Record<string, { precision: number; recall: number; f1: number; support: number }>
  confusion_matrix: number[][]
  ci95?: { accuracy: [number, number]; macro_f1: [number, number] }
}

export interface NL2SQLEval {
  n: number
  raw_validity: number
  selected_validity: number
  final_validity: number
  raw_execution_accuracy: number
  selected_execution_accuracy: number
  final_execution_accuracy: number
  mean_generation_ms: number
  status_counts: Record<string, number>
}

export interface ResearchResults {
  dataset: { train: number; test: number; train_dbs: number; test_dbs: number }
  classifiers: Record<string, ClassifierMetrics>
  main_model: string
  latency: { mean_ms: number; p95_ms: number }
  analyzer_latency_ms: number
  significance: Record<string, { only_a: number; only_b: number; p_value: number }>
  gold_audit: { total: number; pass_rate: number; counts: Record<string, number> }
  permissions: { n: number; accuracy: number; violations: number }
  repair: Record<string, { n: number; verified_rate: number; exact_rate: number } | { mean: number; p95: number }>
  generator: string
  nl2sql_by_generator: Record<string, NL2SQLEval>
  nl2sql: NL2SQLEval
  attributions: { class: ErrorClass; sql: string; top_tokens: string[]; figure: string }[]
  figures: string[]
}
