import { getClientId } from './clientId'
import type {
  AnalyzeResponse,
  BatchRow,
  DatabaseSchema,
  ExampleDatabase,
  ExampleSchemaDetail,
  ExecuteResult,
  Health,
  HistoryItem,
  HistoryKind,
  HistoryPage,
  Job,
  Label,
  Metrics,
  NL2SQLResult,
  ResearchResults,
  SavedSchema,
  SavedSchemaSummary,
  SchemaContextBody,
  AccessPolicy,
} from './types'

export const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, '') ?? '/api/v1'

/** An error the API (or the network) reported, with a message fit for the user. */
export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

function detailMessage(detail: unknown): string | null {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    // FastAPI validation errors: [{loc: [...], msg: "..."}]
    return detail
      .map((d) => {
        const loc = Array.isArray(d?.loc) ? d.loc.filter((p: unknown) => p !== 'body').join('.') : ''
        return loc ? `${loc}: ${d?.msg}` : String(d?.msg ?? d)
      })
      .join('; ')
  }
  return null
}

interface RequestOptions {
  method?: string
  body?: unknown
  form?: FormData
  query?: Record<string, string | number | boolean | undefined | null>
  signal?: AbortSignal
  timeoutMs?: number
}

export async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const url = new URL(API_BASE + path, window.location.origin)
  for (const [k, v] of Object.entries(opts.query ?? {})) {
    if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, String(v))
  }
  const headers: Record<string, string> = { 'X-Client-Id': getClientId(), Accept: 'application/json' }
  let body: BodyInit | undefined
  if (opts.form) body = opts.form
  else if (opts.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(opts.body)
  }
  const controller = new AbortController()
  const onAbort = () => controller.abort()
  opts.signal?.addEventListener('abort', onAbort)
  const timer = setTimeout(() => controller.abort(), opts.timeoutMs ?? 120_000)
  let res: Response
  try {
    res = await fetch(url, { method: opts.method ?? (body ? 'POST' : 'GET'), headers, body, signal: controller.signal })
  } catch (e) {
    if (opts.signal?.aborted) throw e
    if (controller.signal.aborted) throw new ApiError(0, 'The request timed out. The server may be busy; try again.')
    throw new ApiError(0, 'Cannot reach the SQLDiagnose server. Check that the API is running (make api).')
  } finally {
    clearTimeout(timer)
    opts.signal?.removeEventListener('abort', onAbort)
  }
  if (res.status === 204) return undefined as T
  const text = await res.text()
  let data: unknown
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = null
  }
  if (!res.ok) {
    const msg = detailMessage((data as { detail?: unknown } | null)?.detail) ?? (text.slice(0, 200) || res.statusText)
    throw new ApiError(res.status, msg)
  }
  return data as T
}

export const api = {
  health: () => request<Health>('/health', { timeoutMs: 8000 }),
  metrics: () => request<Metrics>('/metrics'),
  labels: () => request<Label[]>('/labels'),
  databases: () => request<ExampleDatabase[]>('/databases'),
  exampleSchema: (dbId: string) => request<ExampleSchemaDetail>(`/schemas/${encodeURIComponent(dbId)}`),

  analyze: (body: { query: string; explain?: boolean; explain_method?: 'gxi' | 'ig'; repair?: boolean } & SchemaContextBody, signal?: AbortSignal) =>
    request<AnalyzeResponse>('/analyze', { body, signal }),
  batch: (body: { queries: string[]; repair: boolean } & SchemaContextBody) =>
    request<BatchRow[]>('/batch', { body, timeoutMs: 600_000 }),
  upload: (file: File, opts: { repair: boolean; db_id?: string; schema_id?: string; access_policy?: AccessPolicy }) => {
    const form = new FormData()
    form.append('file', file)
    const { access_policy, ...query } = opts
    if (access_policy) form.append('access_policy', JSON.stringify(access_policy))
    return request<BatchRow[]>('/upload', { form, query, timeoutMs: 600_000 })
  },
  execute: (body: { query: string; db_id?: string; schema_id?: string; max_rows?: number }) =>
    request<ExecuteResult>('/execute', { body }),

  submitNl2sql: (body: { question: string; num_candidates: number } & SchemaContextBody) =>
    request<Job<NL2SQLResult>>('/nl2sql/jobs', { body }),
  nl2sqlJob: (id: string, signal?: AbortSignal) => request<Job<NL2SQLResult>>(`/nl2sql/jobs/${id}`, { signal }),
  cancelNl2sqlJob: (id: string) => request<Job<NL2SQLResult>>(`/nl2sql/jobs/${id}`, { method: 'DELETE' }),

  parseDdl: (ddl: string, dialect: string) =>
    request<{ database_schema: DatabaseSchema }>('/schemas/parse-ddl', { body: { ddl, dialect } }),
  parseLive: (engine: 'postgresql' | 'mysql', connection: Record<string, unknown>) =>
    request<{ database_schema: DatabaseSchema }>('/schemas/parse-live', { body: { engine, connection }, timeoutMs: 60_000 }),

  savedSchemas: () => request<SavedSchemaSummary[]>('/workspace/schemas'),
  savedSchema: (id: string) => request<SavedSchema>(`/workspace/schemas/${id}`),
  createSavedSchema: (body: { name: string; source: string; database_schema: DatabaseSchema; access_policy?: AccessPolicy | null }) =>
    request<SavedSchema>('/workspace/schemas', { body }),
  uploadSqlite: (file: File, name: string, keepDatabase: boolean) => {
    const form = new FormData()
    form.append('file', file)
    if (name) form.append('name', name)
    form.append('keep_database', String(keepDatabase))
    return request<SavedSchema>('/workspace/schemas/sqlite', { form, timeoutMs: 300_000 })
  },
  updateSavedSchema: (id: string, body: { name?: string; database_schema?: DatabaseSchema; access_policy?: AccessPolicy | null; clear_access_policy?: boolean }) =>
    request<SavedSchema>(`/workspace/schemas/${id}`, { method: 'PATCH', body }),
  deleteSavedSchema: (id: string) => request<void>(`/workspace/schemas/${id}`, { method: 'DELETE' }),

  history: (params: { kind?: HistoryKind; search?: string; limit?: number; offset?: number }) =>
    request<HistoryPage>('/workspace/history', { query: params }),
  historyItem: (id: string) => request<HistoryItem>(`/workspace/history/${id}`),
  deleteHistory: (id: string) => request<void>(`/workspace/history/${id}`, { method: 'DELETE' }),
  clearHistory: () => request<{ deleted: number }>('/workspace/history', { method: 'DELETE' }),

  results: () => request<ResearchResults>('/results'),
  figureUrl: (name: string) => `${API_BASE}/results/figures/${encodeURIComponent(name)}`,
}
