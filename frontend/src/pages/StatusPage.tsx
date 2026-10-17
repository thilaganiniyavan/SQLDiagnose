import { useQuery } from '@tanstack/react-query'
import { Activity, BookOpen, Brain, CheckCircle2, Cpu, Database, ExternalLink, FolderOpen, Plug, XCircle } from 'lucide-react'
import type { ReactNode } from 'react'
import { BarList } from '../components/charts'
import ClassBadge from '../components/ClassBadge'
import { Callout, Card, CardHeader, PageHeader, Pill, Skeleton, Stat } from '../components/ui'
import { api } from '../lib/api'
import { CLASS_ORDER, classLabel } from '../lib/classes'
import { duration, int, ms, pct } from '../lib/format'
import { useHealth, useLabels } from '../lib/queries'

function Row({ icon, label, children }: { icon: ReactNode; label: string; children: ReactNode }) {
  return (
    <div className="flex items-start gap-3 border-b border-line px-5 py-3 last:border-0">
      <span className="mt-0.5 text-ink-muted">{icon}</span>
      <div className="min-w-0 flex-1">
        <p className="text-[13px] text-ink-muted">{label}</p>
        <div className="mt-0.5 text-sm text-ink">{children}</div>
      </div>
    </div>
  )
}

const Yes = ({ children }: { children: ReactNode }) => (
  <span className="inline-flex items-center gap-1.5"><CheckCircle2 className="size-4 text-good-text" />{children}</span>
)
const No = ({ children }: { children: ReactNode }) => (
  <span className="inline-flex items-center gap-1.5"><XCircle className="size-4 text-ink-muted" />{children}</span>
)

export default function StatusPage() {
  const health = useHealth()
  const metrics = useQuery({ queryKey: ['metrics'], queryFn: api.metrics, refetchInterval: 10_000, enabled: !health.isError })
  const labels = useLabels()
  const h = health.data
  const m = metrics.data

  return (
    <>
      <PageHeader
        title="Service status"
        description="What is running on the server, and what it has done since it started."
        actions={
          <a href="/docs" target="_blank" rel="noreferrer" className="inline-flex h-9 items-center gap-2 rounded-lg border border-line-strong bg-surface px-3.5 text-sm font-medium shadow-card hover:bg-surface-2">
            <BookOpen className="size-4" /> API docs <ExternalLink className="size-3.5 text-ink-muted" />
          </a>
        }
      />
      {health.isError && <Callout tone="critical" title="The API is not reachable" className="mb-6">{(health.error as Error).message}</Callout>}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Diagnoses" value={m ? int(m.diagnoses) : '—'} sub={m ? `mean ${ms(m.mean_diagnosis_latency_ms)}` : undefined} />
        <Stat label="Repairs" value={m ? int(m.repairs) : '—'} sub={m && m.repairs ? `${pct(m.repairs_successful / m.repairs, 0)} verified` : 'none yet'} />
        <Stat label="Requests" value={m ? int(Object.values(m.requests).reduce((a, b) => a + b, 0)) : '—'} sub={m ? Object.entries(m.requests).map(([k, v]) => `${k} ${v}`).join(' · ') || 'none yet' : undefined} />
        <Stat label="Uptime" value={m ? duration(m.uptime_s) : '—'} sub={h ? `version ${h.version}` : undefined} />
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader icon={<Activity className="size-4" />} title="Components" />
          {!h ? (
            <div className="space-y-2 p-5">{[1, 2, 3].map((i) => <Skeleton key={i} className="h-10" />)}</div>
          ) : (
            <div>
              <Row icon={<CheckCircle2 className="size-4" />} label="Rule-based analyzer & repair engine">
                <Yes>Always on</Yes>
              </Row>
              <Row icon={<Brain className="size-4" />} label="Neural classifier">
                {h.model_loaded && h.model ? (
                  <div className="space-y-1">
                    <Yes>{h.model.backbone}</Yes>
                    <p className="text-xs text-ink-muted">
                      {(h.model.parameters / 1e6).toFixed(1)} M parameters
                      {h.model.validation?.macro_f1 !== undefined && ` · validation macro-F1 ${pct(h.model.validation.macro_f1)}`} · {h.model.path}
                    </p>
                  </div>
                ) : (
                  <No>Not loaded — the analyzer still gives verified verdicts. Install it with <code className="font-mono">make model</code>.</No>
                )}
              </Row>
              <Row icon={<Cpu className="size-4" />} label="NL→SQL generator">
                {!h.generator ? (
                  <No>Not configured</No>
                ) : (
                  <div className="space-y-1">
                    {h.generator_loaded ? <Yes>{h.generator}</Yes> : <span>{h.generator} <Pill>loads on first question</Pill></span>}
                    {h.generator_error && <p className="text-xs text-critical-text">Last load failed: {h.generator_error}</p>}
                  </div>
                )}
              </Row>
              <Row icon={<Database className="size-4" />} label="Example databases">
                {h.example_databases} schemas · {h.executable_databases ? <>{h.executable_databases} with data (queries can be run)</> : 'no data installed (make data)'}
              </Row>
              <Row icon={<FolderOpen className="size-4" />} label="Workspace (history & saved schemas)">
                {h.workspace_enabled ? <Yes>Enabled</Yes> : <No>Disabled</No>}
              </Row>
              <Row icon={<Plug className="size-4" />} label="Live database introspection">
                {h.live_schema_enabled ? <Yes>Enabled</Yes> : <No>Disabled</No>}
              </Row>
            </div>
          )}
        </Card>

        <Card>
          <CardHeader title="Verdicts since start" subtitle="How often each class was found by this server" />
          <div className="px-4 py-4">
            {m && m.diagnoses > 0 ? (
              <BarList
                ariaLabel="Verdicts per class"
                data={CLASS_ORDER.map((c) => ({ key: c, label: classLabel(c), value: m.class_counts[c] ?? 0 }))}
              />
            ) : (
              <p className="px-1 text-sm text-ink-muted">No queries checked yet.</p>
            )}
          </div>
        </Card>
      </div>

      <Card className="mt-6">
        <CardHeader title="The eight classes" subtitle="Every verdict is one of these. When a query has several problems, the first one an engine would reject is reported." />
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <tbody>
              {(labels.data ?? []).map((l) => (
                <tr key={l.name} className="border-b border-line last:border-0">
                  <td className="w-56 px-5 py-2.5 align-top">
                    <ClassBadge value={l.name} />
                  </td>
                  <td className="px-2 py-2.5 align-top font-mono text-xs text-ink-muted">{l.name}</td>
                  <td className="px-5 py-2.5 text-ink-2">{l.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  )
}
