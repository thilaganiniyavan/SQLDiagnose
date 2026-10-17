import { useMutation, useQuery } from '@tanstack/react-query'
import { ArrowRight, Check, CircleAlert, Clock, Cpu, Download, Loader2, MessageSquareText, Send, Wand2, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import ClassBadge from '../components/ClassBadge'
import { openDatabasePicker } from '../components/Layout'
import QueryRunner from '../components/QueryRunner'
import SqlBlock from '../components/SqlBlock'
import { Button, Callout, Card, CardHeader, CopyButton, EmptyState, Field, PageHeader, Pill, Textarea } from '../components/ui'
import { cx } from '../lib/cx'
import { ApiError, api } from '../lib/api'
import { classLabel } from '../lib/classes'
import { QUESTION_EXAMPLES } from '../lib/examples'
import { duration, ms, pct } from '../lib/format'
import { useHealth } from '../lib/queries'
import type { Job, NL2SQLResult, NL2SQLStatus } from '../lib/types'
import { useApplyContext, useDatabase } from '../state/database'
import { useSessionState } from '../state/session'

const STATUS: Record<NL2SQLStatus, { tone: 'good' | 'warning' | 'critical'; title: string; text: string }> = {
  valid: { tone: 'good', title: 'Valid SQL', text: 'The first generated query passed every check.' },
  valid_alternative: { tone: 'good', title: 'Valid SQL (alternative)', text: 'The first candidate had problems; another candidate passed every check.' },
  repaired: { tone: 'good', title: 'Valid SQL after repair', text: 'No candidate was valid; the best one was repaired and verified.' },
  invalid: { tone: 'critical', title: 'No valid SQL', text: 'Neither the candidates nor the repair produced a valid query. Try rephrasing the question or using the schema’s names.' },
  no_candidate: { tone: 'critical', title: 'Nothing generated', text: 'The generator returned no SQL. Try rephrasing the question.' },
}

interface ActiveJob {
  id: string
  question: string
  startedAt: number
}

function useTicker(active: boolean) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!active) return
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [active])
  return now
}

function Progress({ job, startedAt, modelLoaded, onCancel }: { job: Job<NL2SQLResult> | undefined; startedAt: number; modelLoaded: boolean; onCancel: () => void }) {
  const now = useTicker(true)
  const elapsed = (now - startedAt) / 1000
  // the loading step is only shown when the model was not loaded yet when the question was asked
  const [withLoading] = useState(!modelLoaded)
  const phase = !job || job.status === 'queued' ? 'queued' : job.phase === 'loading_model' ? 'loading' : 'generating'
  const steps = [
    { key: 'queued', label: job?.status === 'queued' && job.queue_position > 1 ? `Waiting in queue (position ${job.queue_position})` : 'Queued' },
    ...(withLoading || phase === 'loading' ? [{ key: 'loading', label: 'Loading the language model (first request only; may download ~1 GB)' }] : []),
    { key: 'generating', label: 'Generating candidates, verifying and repairing' },
  ]
  const at = steps.findIndex((s) => s.key === phase)
  return (
    <Card>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-3.5">
        <div className="flex items-center gap-2.5">
          <Loader2 className="size-4 animate-spin text-accent-text" />
          <p className="text-[15px] font-semibold">Working on it…</p>
        </div>
        <div className="flex items-center gap-3">
          <span className="inline-flex items-center gap-1 text-sm text-ink-2 tabular-nums" aria-label="Elapsed time">
            <Clock className="size-3.5" /> {duration(elapsed)}
          </span>
          {job?.status === 'queued' && (
            <Button size="sm" variant="ghost" icon={<X className="size-3.5" />} onClick={onCancel}>
              Cancel
            </Button>
          )}
        </div>
      </div>
      <ol className="space-y-2.5 px-5 py-4" aria-label="Progress">
        {steps.map((s, i) => {
          const done = i < at
          const current = i === at
          return (
            <li key={s.key} aria-current={current ? 'step' : undefined} className={cx('flex items-center gap-2.5 text-sm', current ? 'text-ink' : done ? 'text-ink-2' : 'text-ink-muted')}>
              <span className={cx('flex size-5 items-center justify-center rounded-full border', done ? 'border-good bg-good-soft text-good-text' : current ? 'border-accent text-accent-text' : 'border-line-strong')}>
                {done ? <Check className="size-3" /> : current ? <span className="size-1.5 animate-pulse rounded-full bg-accent" /> : null}
              </span>
              {s.label}
            </li>
          )
        })}
      </ol>
      <p className="border-t border-line px-5 py-2.5 text-xs text-ink-muted">
        On a CPU this takes about a minute per question. You can keep working on other pages; the result will be here and in History.
      </p>
    </Card>
  )
}

function Result({ result }: { result: NL2SQLResult }) {
  const navigate = useNavigate()
  const s = STATUS[result.status] ?? STATUS.invalid
  const ok = result.status !== 'invalid' && result.status !== 'no_candidate'
  return (
    <div className="space-y-4">
      <Card className={ok ? 'border-l-4 border-l-good' : 'border-l-4 border-l-critical'}>
        <div className="space-y-3 px-5 py-4">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <div className="flex items-center gap-2">
                {ok ? <Check className="size-5 text-good-text" /> : <CircleAlert className="size-5 text-critical-text" />}
                <h2 className="text-lg font-semibold">{s.title}</h2>
              </div>
              <p className="mt-0.5 text-sm text-ink-2">{s.text}</p>
            </div>
            <div className="flex flex-wrap gap-1.5">
              <Pill title="Generator model">
                <Cpu className="size-3" /> {result.generator.split('/').pop()}
              </Pill>
              <Pill title="Total time">{ms(result.latency_ms)}</Pill>
            </div>
          </div>
          <p className="text-sm text-ink-muted">
            <span className="font-medium text-ink-2">Question:</span> {result.question}
          </p>
          {result.sql && (
            <SqlBlock
              sql={result.sql}
              actions={
                <>
                  <Button size="sm" variant="primary" icon={<ArrowRight className="size-3.5" />} onClick={() => navigate(`/?q=${encodeURIComponent(result.sql!)}&run=1`)}>
                    Open in Diagnose
                  </Button>
                  <CopyButton text={result.sql} />
                </>
              }
            />
          )}
          {result.prompt_truncated && (
            <Callout tone="warning">The schema was too long for the model’s context and was shortened, which can lower accuracy.</Callout>
          )}
          {result.repair && (
            <Callout tone={result.repair.success ? 'info' : 'warning'} title={result.repair.success ? 'Repaired' : 'Repair failed'}>
              {result.repair.explanation}
            </Callout>
          )}
        </div>
      </Card>

      {result.sql && ok && (
        <Card>
          <CardHeader title="Answer" subtitle="Run the SQL on the selected database (read-only)." />
          <div className="px-5 py-4">
            <QueryRunner sql={result.sql} autoClearKey={result} />
          </div>
        </Card>
      )}

      {result.candidates.length > 0 && (
        <Card>
          <CardHeader title="Candidates" subtitle="Every query the model proposed, in its own ranking, with the analyzer’s verdict." />
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs text-ink-muted">
                <tr className="border-b border-line">
                  <th className="px-5 py-2 font-medium">#</th>
                  <th className="px-2 py-2 font-medium">SQL</th>
                  <th className="px-2 py-2 font-medium">Verdict</th>
                  <th className="px-5 py-2 text-right font-medium">Score</th>
                </tr>
              </thead>
              <tbody>
                {result.candidates.map((c) => (
                  <tr key={c.rank} className={cx('border-b border-line last:border-0', c.sql === result.sql && 'bg-accent-soft')}>
                    <td className="px-5 py-2.5 align-top text-ink-muted tabular-nums">{c.rank}</td>
                    <td className="px-2 py-2.5 align-top">
                      <code className="sql text-[12px] text-ink">{c.sql}</code>
                      {c.issues.length > 0 && <p className="mt-1 text-xs text-ink-muted">{c.issues.join(' · ')}</p>}
                    </td>
                    <td className="px-2 py-2.5 align-top">
                      <ClassBadge value={c.error_class} size="sm" />
                    </td>
                    <td className="px-5 py-2.5 text-right align-top text-ink-2 tabular-nums">{pct(c.confidence, 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  )
}

export default function AskPage() {
  const db = useDatabase()
  const applyContext = useApplyContext()
  const health = useHealth()
  const [question, setQuestion] = useSessionState('ask.question', '')
  const [k, setK] = useSessionState('ask.k', 3)
  const [active, setActive] = useSessionState<ActiveJob | null>('ask.job', () => {
    try {
      const raw = sessionStorage.getItem('sqld.askJob')
      return raw ? (JSON.parse(raw) as ActiveJob) : null
    } catch {
      return null
    }
  })
  const [result, setResult] = useSessionState<NL2SQLResult | null>('ask.result', null)
  const [params, setParams] = useSearchParams()

  useEffect(() => {
    try {
      if (active) sessionStorage.setItem('sqld.askJob', JSON.stringify(active))
      else sessionStorage.removeItem('sqld.askJob')
    } catch {
      /* ignore */
    }
  }, [active])

  // ?history=<id> reopens a stored result
  useEffect(() => {
    const id = params.get('history')
    if (!id) return
    api
      .historyItem(id)
      .then((item) => {
        setQuestion(item.title)
        applyContext(item.context)
        if (item.result) setResult(item.result as NL2SQLResult)
      })
      .catch((e) => toast.error(`Could not open the history entry: ${e.message}`))
    setParams({}, { replace: true })
  }, [params, setParams, applyContext, setQuestion, setResult])

  const job = useQuery({
    queryKey: ['nl2sql-job', active?.id],
    queryFn: ({ signal }) => api.nl2sqlJob(active!.id, signal),
    enabled: !!active,
    refetchInterval: (q) => (q.state.data && ['done', 'error', 'cancelled'].includes(q.state.data.status) ? false : 1500),
    retry: 2,
  })

  useEffect(() => {
    const j = job.data
    if (!active || !j) return
    if (j.status === 'done' && j.result) {
      setResult(j.result)
      setActive(null)
      if (document.hidden) toast.success('Your SQL is ready')
    } else if (j.status === 'error') {
      toast.error(j.error ?? 'Generation failed')
      setActive(null)
    } else if (j.status === 'cancelled') {
      setActive(null)
    }
  }, [job.data, active, setActive, setResult])

  useEffect(() => {
    if (job.error instanceof ApiError && job.error.status === 404) {
      toast.error('The request expired or the server restarted. Please ask again.')
      setActive(null)
    }
  }, [job.error, setActive])

  const submit = useMutation({
    mutationFn: () => api.submitNl2sql({ question: question.trim(), num_candidates: k, ...db.body }),
    onSuccess: (j) => {
      setResult(null)
      setActive({ id: j.id, question: question.trim(), startedAt: Date.now() })
    },
    onError: (e) => toast.error(e.message),
  })

  const cancel = () => {
    if (!active) return
    api.cancelNl2sqlJob(active.id).then(
      () => setActive(null),
      (e) => toast.error(e.message),
    )
  }

  const noSchema = db.selection.kind === 'none'
  const noGenerator = health.data && !health.data.generator
  const canSubmit = question.trim().length >= 3 && !noSchema && !active && !noGenerator
  const suggestions = (db.selection.kind === 'example' && QUESTION_EXAMPLES[db.selection.dbId]) || QUESTION_EXAMPLES.default

  return (
    <>
      <PageHeader
        title="Question → SQL"
        description="Ask a question about your data in plain English. A code language model writes candidate queries; each one is checked, and the best is repaired if needed, so you only get SQL that is valid for your schema."
      />
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0 space-y-4">
          <Card>
            <form
              className="space-y-4 p-5"
              onSubmit={(e) => {
                e.preventDefault()
                if (canSubmit) submit.mutate()
              }}
            >
              <Field label="Your question" htmlFor="question" hint={<>Press <b>Enter</b> to ask, <b>Shift + Enter</b> for a new line. Using the schema’s table and column names helps.</>}>
                <Textarea
                  id="question"
                  rows={3}
                  value={question}
                  maxLength={2000}
                  onChange={(e) => setQuestion(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault()
                      if (canSubmit) submit.mutate()
                    }
                  }}
                  placeholder="e.g. Which country has the most singers?"
                  className="text-[15px]"
                />
              </Field>
              <div className="flex flex-wrap gap-1.5">
                {suggestions.map((s) => (
                  <button key={s} type="button" onClick={() => setQuestion(s)} className="rounded-full border border-line bg-surface-2 px-3 py-1 text-xs text-ink-2 transition-colors hover:border-accent hover:text-ink">
                    {s}
                  </button>
                ))}
              </div>
              <div className="flex flex-wrap items-end justify-between gap-4 border-t border-line pt-4">
                <div>
                  <label htmlFor="k" className="block text-[13px] font-medium">
                    Candidates to try: <span className="tabular-nums">{k}</span>
                  </label>
                  <input id="k" type="range" min={1} max={5} value={k} onChange={(e) => setK(Number(e.target.value))} className="mt-2 w-48 accent-[var(--accent)]" />
                  <p className="text-xs text-ink-muted">More candidates are only generated if the first one is invalid.</p>
                </div>
                <Button
                  type="submit"
                  variant="primary"
                  size="lg"
                  icon={<Send className="size-4" />}
                  disabled={!canSubmit}
                  loading={submit.isPending}
                  title={canSubmit ? undefined : active ? 'A question is already being answered' : noSchema ? 'Choose a database first' : 'Type a question (at least 3 characters)'}
                >
                  Generate SQL
                </Button>
              </div>
            </form>
          </Card>

          {noSchema && (
            <Callout tone="warning" title="Choose a database first" action={<Button size="sm" onClick={openDatabasePicker}>Choose database</Button>}>
              The generator needs a schema to know which tables and columns exist.
            </Callout>
          )}
          {noGenerator && <Callout tone="warning" title="No generator configured">The server has no NL→SQL model configured (api.generator).</Callout>}
          {health.data?.generator_error && !active && (
            <Callout tone="critical" title="The language model failed to load last time">
              {health.data.generator_error} — asking again retries the download.
            </Callout>
          )}

          {active ? (
            <Progress job={job.data} startedAt={active.startedAt} modelLoaded={!!health.data?.generator_loaded} onCancel={cancel} />
          ) : result ? (
            <Result result={result} />
          ) : (
            <Card>
              <EmptyState icon={<MessageSquareText className="size-5" />} title="Ask your first question">
                Pick a suggestion above or write your own. Answers are generated for <b>{db.label}</b>.
              </EmptyState>
            </Card>
          )}
        </div>

        <aside className="space-y-4">
          <Card>
            <CardHeader icon={<Wand2 className="size-4" />} title="How it works" />
            <ol className="space-y-3 px-5 py-4 text-[13px] text-ink-2">
              <li><b className="text-ink">1. Generate.</b> {health.data?.generator?.split('/').pop() ?? 'The model'} writes a query from your question and the schema.</li>
              <li><b className="text-ink">2. Verify.</b> The analyzer compiles it against the schema and applies every rule.</li>
              <li><b className="text-ink">3. Alternatives.</b> If it fails, up to {k} candidates are compared.</li>
              <li><b className="text-ink">4. Repair.</b> If none is valid, the best one is repaired and re-verified.</li>
            </ol>
            <div className="flex items-center gap-2 border-t border-line px-5 py-3 text-xs text-ink-muted">
              <Download className="size-3.5" />
              {health.data?.generator_loaded ? 'Model loaded and ready.' : 'The model loads on the first question.'}
            </div>
          </Card>
          {result?.diagnosis && (
            <Card className="px-5 py-4 text-[13px]">
              <p className="text-ink-muted">Final verdict</p>
              <div className="mt-1">
                <ClassBadge value={result.diagnosis.error_class} />
              </div>
              <p className="mt-2 text-xs text-ink-muted">{classLabel(result.diagnosis.error_class)} · decided by the {result.diagnosis.decided_by}</p>
            </Card>
          )}
        </aside>
      </div>
    </>
  )
}
