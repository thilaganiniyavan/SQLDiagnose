import { useMutation } from '@tanstack/react-query'
import { ChevronDown, Eraser, Lightbulb, Link2, Play, RotateCcw, ShieldCheck, Stethoscope } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import AnalysisView from '../components/AnalysisView'
import ClassBadge from '../components/ClassBadge'
import { openDatabasePicker } from '../components/Layout'
import SchemaBrowser from '../components/SchemaBrowser'
import SqlEditor, { type SqlEditorHandle } from '../components/SqlEditor'
import { Button, Callout, Card, CardHeader, EmptyState, Kbd, PageHeader, Segmented, Skeleton, Switch } from '../components/ui'
import { cx } from '../lib/cx'
import { api } from '../lib/api'
import { EXAMPLE_DB, QUERY_EXAMPLES, type QueryExample } from '../lib/examples'
import { useHealth } from '../lib/queries'
import { load, save } from '../lib/storage'
import type { AnalyzeResponse, SchemaContextBody } from '../lib/types'
import { completionSchema, useApplyContext, useDatabase } from '../state/database'
import { useSessionState } from '../state/session'

const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)

function ExamplesMenu({ onPick }: { onPick: (e: QueryExample) => void }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const close = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false)
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', esc)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', esc)
    }
  }, [open])
  return (
    <div className="relative" ref={ref}>
      <Button size="sm" variant="ghost" icon={<Lightbulb className="size-3.5" />} onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-haspopup="menu">
        Examples
        <ChevronDown className="size-3.5" />
      </Button>
      {open && (
        <div role="menu" className="absolute left-0 z-20 mt-1 w-80 overflow-hidden rounded-lg border border-line bg-surface py-1 shadow-pop">
          <p className="px-3 pt-1.5 pb-1 text-[11px] text-ink-muted">One per error class, on the {EXAMPLE_DB} database</p>
          {QUERY_EXAMPLES.map((e) => (
            <button
              key={e.id}
              role="menuitem"
              type="button"
              onClick={() => {
                onPick(e)
                setOpen(false)
              }}
              className="block w-full px-3 py-2 text-left hover:bg-surface-2"
            >
              <span className="block text-sm font-medium text-ink">{e.title}</span>
              <span className="block truncate font-mono text-[11px] text-ink-muted">{e.query}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

export default function DiagnosePage() {
  const db = useDatabase()
  const applyContext = useApplyContext()
  const health = useHealth()
  const modelLoaded = !!health.data?.model_loaded
  const [query, setQuery] = useState<string>(() => load('sqld.draft', QUERY_EXAMPLES[0].query))
  const [explain, setExplain] = useState<boolean>(() => load('sqld.explain', true))
  const [method, setMethod] = useState<'gxi' | 'ig'>('gxi')
  const [result, setResult] = useSessionState<AnalyzeResponse | null>('diagnose.result', null)
  const [params, setParams] = useSearchParams()
  const editor = useRef<SqlEditorHandle>(null)

  useEffect(() => save('sqld.draft', query), [query])
  useEffect(() => save('sqld.explain', explain), [explain])

  // `context` overrides the selected database for runs that switch database at the same time
  // (examples, links): the new selection only reaches `db.body` on the next render.
  const analyze = useMutation({
    mutationFn: ({ q, context }: { q: string; context?: SchemaContextBody }) =>
      // until the first health check returns, assume the classifier is there (link runs start immediately)
      api.analyze({ query: q, explain: explain && (health.data?.model_loaded ?? true), explain_method: method, repair: true, ...(context ?? db.body) }),
    onSuccess: (r) => setResult(r),
    onError: (e) => toast.error(e.message),
  })
  const { mutate } = analyze

  const run = useCallback(() => {
    if (!query.trim()) {
      toast.info('Type or paste a SQL query first.')
      editor.current?.focus()
      return
    }
    mutate({ q: query })
  }, [query, mutate])

  const pickExample = (e: QueryExample, runNow = false) => {
    setQuery(e.query)
    setResult(null)
    const policy = { restricted_tables: e.restricted ?? [], restricted_columns: [] }
    if (db.selection.kind !== 'example' || db.selection.dbId !== EXAMPLE_DB) toast.info(`Switched to the ${EXAMPLE_DB} database for this example.`)
    db.select({ kind: 'example', dbId: EXAMPLE_DB }, policy)
    if (e.restricted?.length) toast.info(`Restricted table: ${e.restricted.join(', ')} (see the schema panel).`)
    if (runNow) mutate({ q: e.query, context: { db_id: EXAMPLE_DB, ...(e.restricted?.length ? { access_policy: policy } : {}) } })
  }

  // Shareable links: ?q=<sql>&db=<db_id>&run=1, ?example=<id>&run=1, ?history=<id>.
  // URL parameters are external input, applied once and then removed from the address bar.
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (![...params.keys()].length) return
    const example = QUERY_EXAMPLES.find((e) => e.id === params.get('example'))
    const historyId = params.get('history')
    if (historyId) {
      api
        .historyItem(historyId)
        .then((item) => {
          setQuery(item.title)
          if (!applyContext(item.context)) toast.warning('This entry used an inline schema that is not saved; showing the stored result only.')
          if (item.result) setResult(item.result as AnalyzeResponse)
        })
        .catch((e) => toast.error(`Could not open the history entry: ${e.message}`))
    } else if (example) {
      pickExample(example, params.get('run') === '1')
    } else if (params.get('q')) {
      const q = params.get('q')!
      setQuery(q)
      setResult(null)
      const dbId = params.get('db')
      if (dbId) db.select({ kind: 'example', dbId })
      if (params.get('run') === '1') mutate({ q, context: dbId ? { db_id: dbId } : db.body })
    }
    setParams({}, { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params])
  /* eslint-enable react-hooks/set-state-in-effect */

  const shareLink = () => {
    const url = new URL(window.location.origin + '/')
    url.searchParams.set('q', query)
    if (db.selection.kind === 'example') url.searchParams.set('db', db.selection.dbId)
    url.searchParams.set('run', '1')
    navigator.clipboard.writeText(url.toString()).then(
      () => toast.success(db.selection.kind === 'saved' ? 'Link copied (saved schemas are private, so the link opens without a schema)' : 'Link copied'),
      () => toast.error('Could not copy the link'),
    )
  }

  const completion = useMemo(() => completionSchema(db.schema), [db.schema])
  const stale = result && result.diagnosis.query !== query
  const restricted = db.policy.restricted_tables.length + db.policy.restricted_columns.length

  return (
    <>
      <PageHeader
        title="Diagnose & repair"
        description="Paste a SQL query to find out whether it is wrong, why, and get a fix that has been verified against your schema."
      />
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0 space-y-4">
          <Card>
            <div className="flex flex-wrap items-center gap-1 border-b border-line px-3 py-2">
              <ExamplesMenu onPick={pickExample} />
              <Button size="sm" variant="ghost" icon={<Eraser className="size-3.5" />} onClick={() => { setQuery(''); setResult(null); editor.current?.focus() }}>
                Clear
              </Button>
              <Button size="sm" variant="ghost" icon={<Link2 className="size-3.5" />} onClick={shareLink} disabled={!query.trim()}>
                Copy link
              </Button>
            </div>
            <div className="p-3">
              <SqlEditor
                ref={editor}
                value={query}
                onChange={setQuery}
                onRun={run}
                schema={completion}
                placeholder="SELECT name FROM singer WHERE age > 30"
                ariaLabel="SQL query to diagnose"
              />
            </div>
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line px-4 py-3">
              <div className="flex flex-wrap items-center gap-4">
                <Switch
                  checked={explain && modelLoaded}
                  onChange={setExplain}
                  disabled={!modelLoaded}
                  label="Explain the prediction"
                  description={modelLoaded ? 'Highlights the words the classifier relied on' : 'Needs the classifier checkpoint (make model)'}
                />
                {explain && modelLoaded && (
                  <Segmented<'gxi' | 'ig'>
                    label="Explanation method"
                    value={method}
                    onChange={setMethod}
                    options={[
                      { value: 'gxi', label: 'Fast' },
                      { value: 'ig', label: 'Precise' },
                    ]}
                  />
                )}
              </div>
              <div className="flex items-center gap-3">
                <span className="hidden text-xs text-ink-muted sm:inline">
                  <Kbd>{isMac ? '⌘' : 'Ctrl'}</Kbd> + <Kbd>Enter</Kbd>
                </span>
                <Button variant="primary" size="lg" icon={<Play className="size-4" />} onClick={run} loading={analyze.isPending}>
                  Analyze
                </Button>
              </div>
            </div>
          </Card>

          {db.selection.kind === 'none' && (
            <Callout tone="info" title="No schema selected" action={<Button size="sm" onClick={openDatabasePicker}>Choose database</Button>}>
              Grammar and schema-independent rules are checked; table and column names are not.
            </Callout>
          )}

          {stale && !analyze.isPending && (
            <Callout tone="info" action={<Button size="sm" icon={<RotateCcw className="size-3.5" />} onClick={run}>Re-analyze</Button>}>
              The query was edited after this analysis.
            </Callout>
          )}

          {analyze.isPending && !result ? (
            <Card className="space-y-3 p-5">
              <Skeleton className="h-6 w-56" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-16 w-full" />
            </Card>
          ) : result ? (
            <div className={cx('transition-opacity', analyze.isPending && 'opacity-60')}>
              <AnalysisView
                result={result}
                onUseQuery={(sql) => {
                  setQuery(sql)
                  mutate({ q: sql })
                  window.scrollTo({ top: 0, behavior: 'smooth' })
                }}
              />
            </div>
          ) : (
            <Card>
              <EmptyState icon={<Stethoscope className="size-5" />} title="Ready when you are">
                Write a query or pick one of the <b>Examples</b>, then press <b>Analyze</b>. SQLDiagnose checks it against the schema of{' '}
                <b>{db.label}</b>, explains every problem and proposes a verified fix.
              </EmptyState>
            </Card>
          )}
        </div>

        <aside className="space-y-4">
          <Card>
            <CardHeader
              title="Schema"
              subtitle={db.selection.kind === 'none' ? 'No schema selected' : 'Click a name to insert it'}
              actions={<Button size="sm" variant="ghost" onClick={openDatabasePicker}>Change</Button>}
            />
            <div className="scrollbar-thin max-h-[520px] overflow-y-auto px-3 py-3">
              {db.loading ? (
                <div className="space-y-2">
                  {[1, 2, 3].map((i) => <Skeleton key={i} className="h-6" />)}
                </div>
              ) : db.error ? (
                <Callout tone="critical">{db.error}</Callout>
              ) : db.schema ? (
                <SchemaBrowser schema={db.schema} policy={db.policy} onPolicyChange={db.setPolicy} onInsert={(t) => editor.current?.insert(t)} />
              ) : (
                <EmptyState title="No schema">
                  <Button size="sm" onClick={openDatabasePicker}>Choose a database</Button>
                </EmptyState>
              )}
            </div>
            {db.schema && restricted === 0 && (
              <p className="flex items-center gap-1.5 border-t border-line px-4 py-2.5 text-xs text-ink-muted">
                <ShieldCheck className="size-3.5 shrink-0" /> Hover a table or column and click the lock to restrict access to it.
              </p>
            )}
            {restricted > 0 && (
              <div className="flex items-center justify-between gap-2 border-t border-line px-4 py-2.5 text-xs">
                <span className="text-ink-2">
                  {restricted} restricted — queries touching them are <ClassBadge value="PERMISSION_DENIED" size="sm" />
                </span>
                <Button size="sm" variant="ghost" onClick={() => db.setPolicy({ restricted_tables: [], restricted_columns: [] })}>
                  Clear
                </Button>
              </div>
            )}
          </Card>
          <p className="px-1 text-xs text-ink-muted">
            Your recent checks are in <Link to="/history" className="font-medium text-accent-text hover:underline">History</Link>.
          </p>
        </aside>
      </div>
    </>
  )
}
