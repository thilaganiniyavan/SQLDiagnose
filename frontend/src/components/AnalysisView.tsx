import { ArrowRight, Brain, CheckCircle2, CircleAlert, Sparkles, Wrench, XCircle } from 'lucide-react'
import { CLASS_ORDER, DECIDED_BY, ISSUE_SOURCE, classLabel } from '../lib/classes'
import { ms, pct } from '../lib/format'
import type { AnalyzeResponse } from '../lib/types'
import { BarList, TokenHeatmap } from './charts'
import ClassBadge from './ClassBadge'
import DiffView from './DiffView'
import QueryRunner from './QueryRunner'
import SqlBlock from './SqlBlock'
import { Button, Callout, Card, CardHeader, CopyButton, Pill } from './ui'

interface Props {
  result: AnalyzeResponse
  onUseQuery?: (sql: string) => void
}

export default function AnalysisView({ result, onUseQuery }: Props) {
  const { diagnosis: d, repair } = result
  const issues = d.analysis?.issues ?? []
  const fixed = repair?.success && repair.repaired_query ? repair.repaired_query : null

  return (
    <div className="space-y-4" aria-live="polite">
      {/* ---- verdict */}
      <Card className={d.is_error ? 'border-l-4 border-l-critical' : 'border-l-4 border-l-good'}>
        <div className="flex flex-wrap items-start gap-4 px-5 py-4">
          <div className={d.is_error ? 'text-critical-text' : 'text-good-text'}>
            {d.is_error ? <XCircle className="size-7" aria-hidden /> : <CheckCircle2 className="size-7" aria-hidden />}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-lg font-semibold">{d.is_error ? classLabel(d.error_class) : 'No problems found'}</h2>
              <ClassBadge value={d.error_class} size="sm" />
            </div>
            <p className="mt-1 text-sm text-ink-2">{d.is_error ? d.description : 'The query is valid against the selected schema and passes every rule.'}</p>
            <div className="mt-3 flex flex-wrap gap-1.5">
              <Pill title="How certain the verdict is">confidence {pct(d.confidence, 0)}</Pill>
              <Pill title="Which component decided">{DECIDED_BY[d.decided_by] ?? d.decided_by}</Pill>
              <Pill title="Time to diagnose">{ms(d.latency_ms)}</Pill>
              {d.analysis && !d.analysis.schema_checked && (
                <Pill tone="warning" title="Without a schema only grammar and schema-independent rules are checked">
                  no schema — names not checked
                </Pill>
              )}
            </div>
          </div>
        </div>

        {issues.length > 0 && (
          <div className="border-t border-line px-5 py-4">
            <h3 className="mb-2 text-[13px] font-semibold text-ink">
              {issues.length === 1 ? 'Issue' : `${issues.length} issues`} found
            </h3>
            <ol className="space-y-2">
              {issues.map((i, n) => (
                <li key={n} className="flex gap-3 rounded-lg border border-line bg-surface-2/60 px-3 py-2.5">
                  <span className="mt-px flex size-5 shrink-0 items-center justify-center rounded-full bg-surface-3 text-[11px] font-semibold text-ink-2">{n + 1}</span>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm text-ink">{i.message}</p>
                    <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                      <ClassBadge value={i.error_class} size="sm" />
                      <span className="text-[11px] text-ink-muted">via {ISSUE_SOURCE[i.source] ?? i.source}</span>
                      {i.token && <code className="rounded bg-surface-3 px-1.5 py-px font-mono text-[11px] text-ink-2">{i.token}</code>}
                    </div>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        )}

        {d.notes.length > 0 && (
          <div className="border-t border-line px-5 py-3">
            {d.notes.map((n, i) => (
              <p key={i} className="flex gap-2 text-[13px] text-ink-2">
                <Brain className="mt-0.5 size-4 shrink-0 text-ink-muted" aria-hidden />
                {n}
              </p>
            ))}
          </div>
        )}
      </Card>

      {/* ---- repair */}
      {repair && (
        <Card>
          <CardHeader
            icon={<Wrench className="size-4" />}
            title={repair.success ? 'Verified fix' : 'Partial fix'}
            subtitle={
              repair.success
                ? 'The repaired query was re-checked and passes the analyzer.'
                : `Some problems could not be repaired automatically${repair.remaining_error ? ` (${classLabel(repair.remaining_error)} remains)` : ''}.`
            }
            actions={repair.success ? <Pill tone="good"><CheckCircle2 className="size-3" />verified</Pill> : <Pill tone="warning"><CircleAlert className="size-3" />needs attention</Pill>}
          />
          <div className="space-y-4 px-5 py-4">
            {repair.repaired_query && repair.repaired_query !== repair.original_query && (
              <div>
                <p className="mb-1.5 text-xs font-medium text-ink-muted">What changed</p>
                <DiffView before={repair.original_query} after={repair.repaired_query} />
              </div>
            )}
            {repair.repaired_query && (
              <div>
                <p className="mb-1.5 text-xs font-medium text-ink-muted">{repair.success ? 'Repaired query' : 'Best attempt'}</p>
                <SqlBlock
                  sql={repair.repaired_query}
                  actions={
                    <>
                      {onUseQuery && (
                        <Button size="sm" variant={repair.success ? 'primary' : 'secondary'} icon={<ArrowRight className="size-3.5" />} onClick={() => onUseQuery(repair.repaired_query!)}>
                          Use this query
                        </Button>
                      )}
                      <CopyButton text={repair.repaired_query} />
                    </>
                  }
                />
              </div>
            )}
            {repair.steps.length > 0 && (
              <div>
                <p className="mb-1.5 text-xs font-medium text-ink-muted">Steps</p>
                <ol className="space-y-1.5">
                  {repair.steps.map((s, i) => (
                    <li key={i} className="flex flex-wrap items-baseline gap-2 text-sm">
                      <span className="text-xs font-semibold text-ink-muted tabular-nums">{i + 1}.</span>
                      <ClassBadge value={s.error_class} size="sm" />
                      <span className="text-ink-2">{s.description}</span>
                    </li>
                  ))}
                </ol>
              </div>
            )}
            {!repair.success && <Callout tone="warning" title="Why it could not be fully fixed">{repair.explanation}</Callout>}
          </div>
        </Card>
      )}

      {/* ---- run */}
      {(!d.is_error || fixed) && (
        <Card>
          <CardHeader title={fixed ? 'Try the repaired query' : 'Run the query'} subtitle="Read-only, on the selected database's real data." />
          <div className="px-5 py-4">
            <QueryRunner sql={fixed ?? d.query} label={fixed ? 'Run repaired query' : 'Run query'} autoClearKey={result} />
          </div>
        </Card>
      )}

      {/* ---- model */}
      {(d.model || d.explanation) && (
        <Card>
          <CardHeader
            icon={<Sparkles className="size-4" />}
            title="Neural classifier"
            subtitle="A learned second opinion: class probabilities and the words that drove the prediction."
          />
          <div className="grid gap-6 px-5 py-4 xl:grid-cols-2">
            {d.model && (
              <div>
                <p className="mb-2 text-xs font-medium text-ink-muted">
                  Predicts <span className="text-ink">{classLabel(d.model.error_class)}</span> with {pct(d.model.confidence, 0)} probability
                </p>
                <BarList
                  ariaLabel="Class probabilities"
                  max={1}
                  format={(v) => pct(v, 1)}
                  data={CLASS_ORDER.filter((c) => c in d.model!.probabilities)
                    .map((c) => ({ key: c, label: classLabel(c), value: d.model!.probabilities[c], emphasis: c === d.model!.error_class }))
                    .sort((a, b) => b.value - a.value)}
                />
              </div>
            )}
            <div>
              <p className="mb-2 text-xs font-medium text-ink-muted">Which words mattered</p>
              {d.explanation?.query_tokens?.length ? (
                <TokenHeatmap tokens={d.explanation.query_tokens} />
              ) : d.explanation?.error ? (
                <p className="text-sm text-ink-muted">{d.explanation.error}</p>
              ) : (
                <p className="text-sm text-ink-muted">Turn on “Explain the prediction” and analyze again to see token attributions.</p>
              )}
            </div>
          </div>
        </Card>
      )}
    </div>
  )
}
