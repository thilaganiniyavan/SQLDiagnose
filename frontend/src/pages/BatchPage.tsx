import { useMutation } from '@tanstack/react-query'
import { ChevronRight, Download, FileSpreadsheet, FileStack, Play, Search, Upload, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type DragEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { BarList } from '../components/charts'
import ClassBadge from '../components/ClassBadge'
import DiffView from '../components/DiffView'
import { Button, Callout, Card, CardHeader, CopyButton, EmptyState, IconButton, Input, PageHeader, Segmented, Stat, Switch, Textarea } from '../components/ui'
import { cx } from '../lib/cx'
import { api } from '../lib/api'
import { CLASS_ORDER, classLabel } from '../lib/classes'
import { download, splitQueries, toCsv } from '../lib/csv'
import { pct } from '../lib/format'
import type { BatchRow, ErrorClass } from '../lib/types'
import { useApplyContext, useDatabase } from '../state/database'
import { useSessionState } from '../state/session'

const SAMPLE = `SELECT Name FROM singer
SELECT Nmae FROM singer
SELECT count(*) FROM singers
SELECT Name FROM singer WHERE Age = NULL
SELEC Name, Country FROM singer WHERE Age > 30`

const SAMPLE_CSV = `query,db_id
SELECT Name FROM singer,concert_singer
SELECT Nmae FROM singer,concert_singer
"SELECT name FROM singer WHERE age > 'thirty'",concert_singer
`
const MAX_CSV_MB = 10

interface BatchState {
  rows: BatchRow[]
  source: string
}

function Row({ r, index }: { r: BatchRow; index: number }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <tr className={cx('border-b border-line align-top hover:bg-surface-2/60', open && 'bg-surface-2/60')}>
        <td className="py-2.5 pl-4">
          <IconButton label={open ? 'Collapse' : 'Expand'} onClick={() => setOpen(!open)} className="size-6" aria-expanded={open}>
            <ChevronRight className={cx('size-3.5 transition-transform', open && 'rotate-90')} />
          </IconButton>
        </td>
        <td className="py-2.5 pr-2 text-xs text-ink-muted tabular-nums">{index + 1}</td>
        <td className="max-w-[28rem] py-2.5 pr-3">
          <code className="sql line-clamp-2 block text-[12px] text-ink">{r.query || <span className="text-ink-muted italic">(empty)</span>}</code>
        </td>
        <td className="py-2.5 pr-3">
          <ClassBadge value={r.error_class} size="sm" />
        </td>
        <td className="hidden max-w-[22rem] py-2.5 pr-3 text-xs text-ink-2 lg:table-cell">
          <span className="line-clamp-2">{r.issues[0] ?? '—'}</span>
        </td>
        <td className="py-2.5 pr-4 text-xs">
          {r.repair_success === undefined || !r.is_error ? (
            <span className="text-ink-muted">—</span>
          ) : r.repair_success ? (
            <span className="font-medium text-good-text">fixed</span>
          ) : (
            <span className="text-warning-text">not fixed</span>
          )}
        </td>
      </tr>
      {open && (
        <tr className="border-b border-line bg-surface-2/40">
          <td />
          <td colSpan={5} className="space-y-3 py-3 pr-4">
            {r.issues.length > 0 && (
              <ul className="list-disc space-y-0.5 pl-4 text-[13px] text-ink-2">
                {r.issues.map((i, n) => <li key={n}>{i}</li>)}
              </ul>
            )}
            {r.repaired_query && (
              <div className="space-y-1.5">
                <DiffView before={r.query} after={r.repaired_query} />
                <CopyButton text={r.repaired_query} label="Copy fix" />
              </div>
            )}
            {r.repair_success === false && r.repair_explanation && <p className="text-xs text-ink-muted">{r.repair_explanation}</p>}
            <p className="text-xs text-ink-muted">
              Decided by {r.decided_by}, confidence {pct(r.confidence, 0)}
              {r.model_prediction && r.model_prediction !== r.error_class && <> · classifier suggested {classLabel(r.model_prediction)}</>}
            </p>
          </td>
        </tr>
      )}
    </>
  )
}

export default function BatchPage() {
  const db = useDatabase()
  const applyContext = useApplyContext()
  const [mode, setMode] = useSessionState<'paste' | 'csv'>('batch.mode', 'paste')
  const [text, setText] = useSessionState('batch.text', SAMPLE)
  const [split, setSplit] = useSessionState<'lines' | 'semicolons'>('batch.split', 'lines')
  const [file, setFile] = useState<File | null>(null)
  const [repair, setRepair] = useSessionState('batch.repair', true)
  const [state, setState] = useSessionState<BatchState | null>('batch.result', null)
  const [filter, setFilter] = useState<ErrorClass | 'ALL' | 'ERRORS'>('ALL')
  const [search, setSearch] = useState('')
  const [dragging, setDragging] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)
  const [params, setParams] = useSearchParams()

  useEffect(() => {
    const id = params.get('history')
    if (!id) return
    api
      .historyItem(id)
      .then((item) => {
        applyContext(item.context)
        if (Array.isArray(item.result)) setState({ rows: item.result as BatchRow[], source: item.title })
        else toast.warning('This batch was too large to store its rows.')
      })
      .catch((e) => toast.error(`Could not open the history entry: ${e.message}`))
    setParams({}, { replace: true })
  }, [params, setParams, applyContext, setState])

  const queries = useMemo(() => splitQueries(text, split), [text, split])
  const hasPolicy = db.policy.restricted_tables.length + db.policy.restricted_columns.length > 0

  const run = useMutation({
    mutationFn: async (): Promise<BatchState> => {
      if (mode === 'paste') {
        const rows = await api.batch({ queries, repair, ...db.body })
        return { rows, source: `${rows.length} pasted queries` }
      }
      const rows = await api.upload(file!, {
        repair,
        db_id: db.selection.kind === 'example' ? db.selection.dbId : undefined,
        schema_id: db.selection.kind === 'saved' ? db.selection.id : undefined,
        access_policy: hasPolicy ? db.policy : undefined,
      })
      return { rows, source: file!.name }
    },
    onSuccess: (s) => {
      setState(s)
      setFilter('ALL')
      setSearch('')
      toast.success(`Checked ${s.rows.length} quer${s.rows.length === 1 ? 'y' : 'ies'}`)
    },
    onError: (e) => toast.error(e.message),
  })

  const pickFile = (f: File | undefined) => {
    if (!f) return
    if (!/\.csv$/i.test(f.name) && f.type !== 'text/csv') return toast.error('Please choose a .csv file.')
    if (f.size > MAX_CSV_MB * 1024 * 1024) return toast.error(`The file is larger than ${MAX_CSV_MB} MB.`)
    setFile(f)
  }
  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setDragging(false)
    pickFile(e.dataTransfer.files?.[0])
  }

  const rows = useMemo(() => state?.rows ?? [], [state])
  const counts = useMemo(() => {
    const c: Record<string, number> = {}
    for (const r of rows) c[r.error_class] = (c[r.error_class] ?? 0) + 1
    return c
  }, [rows])
  const errors = rows.filter((r) => r.is_error).length
  const repaired = rows.filter((r) => r.repair_success).length
  const term = search.trim().toLowerCase()
  const visible = rows
    .map((r, i) => ({ r, i }))
    .filter(({ r }) => (filter === 'ALL' ? true : filter === 'ERRORS' ? r.is_error : r.error_class === filter))
    .filter(({ r }) => !term || r.query.toLowerCase().includes(term) || r.issues.some((x) => x.toLowerCase().includes(term)))

  const canRun = mode === 'paste' ? queries.length > 0 && queries.length <= 500 : !!file

  const exportCsv = () =>
    download(
      'sqldiagnose_batch.csv',
      toCsv(rows as unknown as Record<string, unknown>[], ['query', 'error_class', 'is_error', 'confidence', 'decided_by', 'issues', 'model_prediction', 'repair_success', 'repaired_query', 'repair_explanation']),
    )

  return (
    <>
      <PageHeader title="Batch check" description="Check many queries at once — paste them or upload a CSV — and export the verdicts and verified fixes." />

      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-3">
          <Segmented<'paste' | 'csv'>
            label="Input"
            value={mode}
            onChange={setMode}
            options={[
              { value: 'paste', label: 'Paste queries', icon: <FileStack className="size-3.5" /> },
              { value: 'csv', label: 'Upload CSV', icon: <FileSpreadsheet className="size-3.5" /> },
            ]}
          />
          <p className="text-xs text-ink-muted">
            Checked against <b className="text-ink-2">{db.label}</b>
            {hasPolicy && ' with your access restrictions'}
          </p>
        </div>
        <div className="p-5">
          {mode === 'paste' ? (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <Segmented<'lines' | 'semicolons'>
                  label="Split queries by"
                  value={split}
                  onChange={setSplit}
                  options={[
                    { value: 'lines', label: 'One per line' },
                    { value: 'semicolons', label: 'Separated by ;' },
                  ]}
                />
                <span className={cx('text-xs tabular-nums', queries.length > 500 ? 'text-critical-text' : 'text-ink-muted')}>
                  {queries.length} quer{queries.length === 1 ? 'y' : 'ies'}
                  {queries.length > 500 && ' — at most 500 per batch'}
                </span>
              </div>
              <Textarea value={text} onChange={(e) => setText(e.target.value)} rows={9} spellCheck={false} className="font-mono text-[13px]" aria-label="Queries to check" placeholder={'SELECT * FROM users\nSELECT id FROM orders'} />
            </div>
          ) : (
            <div className="space-y-3">
              <div
                onDragOver={(e) => {
                  e.preventDefault()
                  setDragging(true)
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={onDrop}
                className={cx('flex flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors', dragging ? 'border-accent bg-accent-soft' : 'border-line-strong')}
              >
                <Upload className="mb-2 size-6 text-ink-muted" />
                {file ? (
                  <div className="flex items-center gap-2">
                    <FileSpreadsheet className="size-4 text-accent-text" />
                    <span className="font-medium">{file.name}</span>
                    <span className="text-xs text-ink-muted">{(file.size / 1024).toFixed(1)} KB</span>
                    <IconButton label="Remove file" onClick={() => setFile(null)} className="size-6">
                      <X className="size-3.5" />
                    </IconButton>
                  </div>
                ) : (
                  <p className="text-sm text-ink-2">Drop a CSV file here, or</p>
                )}
                <Button size="sm" className="mt-3" onClick={() => fileInput.current?.click()}>
                  {file ? 'Choose another file' : 'Choose file'}
                </Button>
                <input ref={fileInput} type="file" accept=".csv,text/csv" className="hidden" onChange={(e) => { pickFile(e.target.files?.[0]); e.target.value = '' }} />
              </div>
              <p className="text-xs text-ink-muted">
                Needs a header row with a <code className="font-mono">query</code> column. An optional <code className="font-mono">db_id</code> column checks each row against that example database; other rows use{' '}
                <b>{db.label}</b>.{' '}
                <button type="button" className="font-medium text-accent-text hover:underline" onClick={() => download('sqldiagnose_sample.csv', SAMPLE_CSV)}>
                  Download a sample CSV
                </button>
              </p>
            </div>
          )}
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4">
            <Switch checked={repair} onChange={setRepair} label="Repair erroneous queries" description="Slower, but every fix is verified" />
            <Button variant="primary" size="lg" icon={<Play className="size-4" />} onClick={() => run.mutate()} disabled={!canRun} loading={run.isPending}>
              Check {mode === 'paste' ? `${queries.length || ''} quer${queries.length === 1 ? 'y' : 'ies'}` : 'file'}
            </Button>
          </div>
        </div>
      </Card>

      {run.isPending && (
        <Callout tone="info" className="mt-4">
          Checking… {repair && 'Repairing takes a little longer for queries with several errors.'}
        </Callout>
      )}

      {state && rows.length > 0 && (
        <div className="mt-6 space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Queries" value={rows.length} sub={state.source} />
            <Stat label="With errors" value={errors} sub={`${pct(errors / rows.length, 0)} of all`} />
            <Stat label="Correct" value={rows.length - errors} sub={`${pct((rows.length - errors) / rows.length, 0)} of all`} />
            <Stat label="Verified fixes" value={rows.some((r) => r.repair_success !== undefined) ? repaired : '—'} sub={errors ? `${pct(repaired / errors, 0)} of errors` : 'nothing to fix'} />
          </div>

          <div className="grid gap-4 xl:grid-cols-[320px_minmax(0,1fr)]">
            <Card>
              <CardHeader title="By class" subtitle="Click a class to filter the table" />
              <div className="px-3 py-3">
                <BarList
                  ariaLabel="Queries per error class"
                  labelWidth="9rem"
                  data={CLASS_ORDER.filter((c) => counts[c]).map((c) => ({
                    key: c,
                    label: (
                      <button type="button" onClick={() => setFilter(filter === c ? 'ALL' : c)} className={cx('hover:underline', filter === c && 'font-semibold text-ink')}>
                        {classLabel(c)}
                      </button>
                    ),
                    value: counts[c],
                    emphasis: filter === c,
                    tooltip: `${classLabel(c)}: ${counts[c]}`,
                  }))}
                />
              </div>
            </Card>

            <Card className="min-w-0">
              <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-3">
                <div className="flex flex-wrap gap-1">
                  {(['ALL', 'ERRORS'] as const).map((f) => (
                    <button key={f} type="button" onClick={() => setFilter(f)} className={cx('rounded-full px-3 py-1 text-xs font-medium', filter === f ? 'bg-ink text-page' : 'bg-surface-2 text-ink-2 hover:text-ink')}>
                      {f === 'ALL' ? `All (${rows.length})` : `Errors (${errors})`}
                    </button>
                  ))}
                  {filter !== 'ALL' && filter !== 'ERRORS' && (
                    <button type="button" onClick={() => setFilter('ALL')} className="inline-flex items-center gap-1 rounded-full bg-ink px-3 py-1 text-xs font-medium text-page">
                      {classLabel(filter)} <X className="size-3" />
                    </button>
                  )}
                </div>
                <div className="relative ml-auto min-w-48">
                  <Search className="pointer-events-none absolute top-2 left-2.5 size-4 text-ink-muted" />
                  <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search queries and issues" className="h-8 pl-8 text-[13px]" aria-label="Search results" />
                </div>
                <Button size="sm" icon={<Download className="size-3.5" />} onClick={exportCsv}>
                  CSV
                </Button>
                <Button size="sm" variant="ghost" onClick={() => download('sqldiagnose_batch.json', JSON.stringify(rows, null, 2), 'application/json')}>
                  JSON
                </Button>
              </div>
              <div className="scrollbar-thin max-h-[640px] overflow-auto">
                <table className="w-full text-left text-sm">
                  <thead className="sticky top-0 z-10 bg-surface text-xs text-ink-muted">
                    <tr className="border-b border-line">
                      <th className="w-10 py-2 pl-4" />
                      <th className="w-8 py-2 pr-2 font-medium">#</th>
                      <th className="py-2 pr-3 font-medium">Query</th>
                      <th className="py-2 pr-3 font-medium">Verdict</th>
                      <th className="hidden py-2 pr-3 font-medium lg:table-cell">Main issue</th>
                      <th className="py-2 pr-4 font-medium">Repair</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visible.map(({ r, i }) => (
                      <Row key={i} r={r} index={i} />
                    ))}
                  </tbody>
                </table>
                {visible.length === 0 && <EmptyState title="No rows match the filter" />}
              </div>
            </Card>
          </div>
        </div>
      )}
    </>
  )
}
