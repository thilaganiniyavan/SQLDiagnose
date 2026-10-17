import { useQuery } from '@tanstack/react-query'
import { BarChart3, FlaskConical, Image as ImageIcon } from 'lucide-react'
import { useState } from 'react'
import { ConfusionMatrix, GroupedBars, type Series } from '../components/charts'
import { Callout, Card, CardHeader, EmptyState, PageHeader, Segmented, Skeleton, Stat } from '../components/ui'
import { api } from '../lib/api'
import { CLASS_META, CLASS_ORDER, classLabel } from '../lib/classes'
import { int, ms, pct } from '../lib/format'
import type { ErrorClass, ResearchResults } from '../lib/types'

const SERIES_COLORS = ['var(--cat-1)', 'var(--cat-2)', 'var(--cat-3)']
const FIGURE_CAPTIONS: Record<string, string> = {
  'confusion_matrix.png': 'Confusion matrix',
  'per_class_f1.png': 'F1 per class',
  'repair_by_class.png': 'Repair success by class',
  'nl2sql_pipeline.png': 'NL→SQL: raw vs. verified',
  'training_curve.png': 'Training curve',
  'reliability.png': 'Calibration (reliability diagram)',
  'xai_unknown_column.png': 'Token attributions: unknown column',
  'xai_syntax_error.png': 'Token attributions: syntax error',
  'xai_semantic_error.png': 'Token attributions: semantic error',
}

function short(name: string) {
  return name.replace('CodeBERTa-small-v1', 'CodeBERTa-small').replace(' (no schema input)', ' (query only)')
}

function Body({ r }: { r: ResearchResults }) {
  const [view, setView] = useState<'charts' | 'table'>('charts')
  const main = r.classifiers[r.main_model]
  const baseline = r.classifiers['TF-IDF + LogReg']
  const repairAll = r.repair.ALL as { n: number; verified_rate: number; exact_rate: number }
  const classifierNames = Object.keys(r.classifiers)
  const modelClasses = Object.keys(main.per_class) as ErrorClass[]
  const repairClasses = CLASS_ORDER.filter((c) => c in r.repair)
  const generators = Object.keys(r.nl2sql_by_generator)
  const nlSeries: Series[] = [
    { key: 'raw', label: 'Raw model output', color: SERIES_COLORS[0] },
    { key: 'selected', label: 'Best verified candidate', color: SERIES_COLORS[1] },
    { key: 'final', label: 'After repair', color: SERIES_COLORS[2] },
  ]

  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Error classification accuracy" value={pct(main.accuracy)} sub={`macro-F1 ${pct(main.macro_f1)} · baseline ${pct(baseline?.accuracy)}`} />
        <Stat label="Queries repaired & verified" value={pct(repairAll.verified_rate)} sub={`${pct(repairAll.exact_rate)} restored exactly`} />
        <Stat label="NL→SQL valid after verification" value={pct(r.nl2sql.final_validity)} sub={`raw ${pct(r.nl2sql.raw_validity)} → final`} />
        <Stat label="Correct results (NL→SQL)" value={pct(r.nl2sql.final_execution_accuracy)} sub={`raw ${pct(r.nl2sql.raw_execution_accuracy)} · ${r.nl2sql.n} questions`} />
      </div>
      <p className="text-sm text-ink-2">
        Classifier tested on {int(r.dataset.test)} queries from {r.dataset.test_dbs} databases never seen in training ({int(r.dataset.train)} training queries,{' '}
        {r.dataset.train_dbs} databases). The analyzer passes {pct(r.gold_audit.pass_rate)} of {int(r.gold_audit.total)} human-written Spider queries, and the access-policy check is{' '}
        {pct(r.permissions.accuracy, 0)} correct on {r.permissions.n} cases. Mean classifier latency {ms(r.latency.mean_ms)} (p95 {ms(r.latency.p95_ms)}), analyzer {ms(r.analyzer_latency_ms)}.
      </p>

      <div className="flex justify-end">
        <Segmented<'charts' | 'table'>
          label="View"
          value={view}
          onChange={setView}
          options={[
            { value: 'charts', label: 'Charts', icon: <BarChart3 className="size-3.5" /> },
            { value: 'table', label: 'Tables' },
          ]}
        />
      </div>

      {view === 'charts' ? (
        <>
          <div className="grid gap-6 xl:grid-cols-2">
            <Card>
              <CardHeader title="Classifier comparison" subtitle="Accuracy and macro-F1 on the unseen-database test set" />
              <div className="p-5">
                <GroupedBars
                  ariaLabel="Classifier comparison"
                  categories={classifierNames.map((n) => ({ key: n, label: short(n) }))}
                  series={[
                    { key: 'accuracy', label: 'Accuracy', color: SERIES_COLORS[0] },
                    { key: 'macro_f1', label: 'Macro-F1', color: SERIES_COLORS[1] },
                  ]}
                  values={(c, s) => r.classifiers[c][s as 'accuracy' | 'macro_f1']}
                  format={(v) => pct(v)}
                  labelWidth="13rem"
                />
                {Object.entries(r.significance).map(([k, v]) => (
                  <p key={k} className="mt-3 text-xs text-ink-muted">
                    {short(k)}: McNemar p = {v.p_value.toExponential(1)} ({v.only_a} vs {v.only_b} discordant)
                  </p>
                ))}
              </div>
            </Card>
            <Card>
              <CardHeader title="F1 per class" subtitle="Where each classifier succeeds and struggles" />
              <div className="p-5">
                <GroupedBars
                  ariaLabel="F1 per class"
                  categories={modelClasses.map((c) => ({ key: c, label: classLabel(c) }))}
                  series={classifierNames.map((n, i) => ({ key: n, label: short(n), color: SERIES_COLORS[i] }))}
                  values={(c, s) => r.classifiers[s].per_class[c]?.f1}
                  format={(v) => pct(v, 0)}
                />
              </div>
            </Card>
          </div>

          <div className="grid gap-6 xl:grid-cols-2">
            <Card>
              <CardHeader title={`Confusion matrix — ${short(r.main_model)}`} subtitle="Rows are the true class, columns the prediction; shading is the share of the row" />
              <div className="p-5">
                <ConfusionMatrix labels={modelClasses} matrix={main.confusion_matrix} short={(l) => CLASS_META[l as ErrorClass]?.short ?? l} />
              </div>
            </Card>
            <Card>
              <CardHeader title="Repair by class" subtitle={`${int(repairAll.n)} erroneous test queries · mean ${ms((r.repair.latency_ms as { mean: number }).mean)} per repair`} />
              <div className="p-5">
                <GroupedBars
                  ariaLabel="Repair success by class"
                  categories={repairClasses.map((c) => ({ key: c, label: classLabel(c) }))}
                  series={[
                    { key: 'verified_rate', label: 'Verified fix', color: SERIES_COLORS[0] },
                    { key: 'exact_rate', label: 'Exactly the original', color: SERIES_COLORS[1] },
                  ]}
                  values={(c, s) => (r.repair[c] as Record<string, number>)?.[s]}
                  format={(v) => pct(v, 0)}
                />
              </div>
            </Card>
          </div>

          <Card>
            <CardHeader title="Question → SQL" subtitle={`${r.nl2sql.n} Spider-dev questions, the same for each generator`} />
            <div className="grid gap-8 p-5 lg:grid-cols-2">
              <div>
                <p className="mb-2 text-[13px] font-medium">Valid SQL</p>
                <GroupedBars
                  ariaLabel="NL to SQL validity"
                  categories={generators.map((g) => ({ key: g, label: g.split('/').pop()! }))}
                  series={nlSeries}
                  values={(g, s) => r.nl2sql_by_generator[g][`${s}_validity` as 'raw_validity']}
                  format={(v) => pct(v, 0)}
                  labelWidth="12rem"
                />
              </div>
              <div>
                <p className="mb-2 text-[13px] font-medium">Correct result (execution accuracy)</p>
                <GroupedBars
                  ariaLabel="NL to SQL execution accuracy"
                  categories={generators.map((g) => ({ key: g, label: g.split('/').pop()! }))}
                  series={nlSeries}
                  values={(g, s) => r.nl2sql_by_generator[g][`${s}_execution_accuracy` as 'raw_execution_accuracy']}
                  format={(v) => pct(v, 0)}
                  labelWidth="12rem"
                />
              </div>
            </div>
          </Card>
        </>
      ) : (
        <>
          <Card>
            <CardHeader title="Classifiers" />
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs text-ink-muted">
                  <tr className="border-b border-line">
                    {['System', 'Accuracy', '95% CI', 'Macro-P', 'Macro-R', 'Macro-F1', 'ROC-AUC', 'ECE'].map((h) => (
                      <th key={h} className="px-4 py-2 font-medium">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {classifierNames.map((n) => {
                    const c = r.classifiers[n]
                    return (
                      <tr key={n} className="border-b border-line last:border-0">
                        <td className="px-4 py-2 font-medium">{n}</td>
                        <td className="px-4 py-2 tabular-nums">{pct(c.accuracy)}</td>
                        <td className="px-4 py-2 text-ink-muted tabular-nums">{c.ci95 ? `${pct(c.ci95.accuracy[0])}–${pct(c.ci95.accuracy[1])}` : '—'}</td>
                        <td className="px-4 py-2 tabular-nums">{pct(c.macro_precision)}</td>
                        <td className="px-4 py-2 tabular-nums">{pct(c.macro_recall)}</td>
                        <td className="px-4 py-2 font-semibold tabular-nums">{pct(c.macro_f1)}</td>
                        <td className="px-4 py-2 tabular-nums">{pct(c.macro_roc_auc)}</td>
                        <td className="px-4 py-2 tabular-nums">{c.ece?.toFixed(3) ?? '—'}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </Card>
          <Card>
            <CardHeader title={`Per class — ${short(r.main_model)}`} />
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs text-ink-muted">
                  <tr className="border-b border-line">
                    {['Class', 'Precision', 'Recall', 'F1', 'Support', 'Repair verified', 'Repair exact'].map((h) => (
                      <th key={h} className="px-4 py-2 font-medium">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {modelClasses.map((c) => {
                    const p = main.per_class[c]
                    const rep = r.repair[c] as { verified_rate: number; exact_rate: number } | undefined
                    return (
                      <tr key={c} className="border-b border-line last:border-0">
                        <td className="px-4 py-2">{classLabel(c)}</td>
                        <td className="px-4 py-2 tabular-nums">{pct(p.precision)}</td>
                        <td className="px-4 py-2 tabular-nums">{pct(p.recall)}</td>
                        <td className="px-4 py-2 font-semibold tabular-nums">{pct(p.f1)}</td>
                        <td className="px-4 py-2 tabular-nums">{p.support}</td>
                        <td className="px-4 py-2 tabular-nums">{rep ? pct(rep.verified_rate) : '—'}</td>
                        <td className="px-4 py-2 tabular-nums">{rep ? pct(rep.exact_rate) : '—'}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </Card>
          <Card>
            <CardHeader title="Question → SQL" />
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs text-ink-muted">
                  <tr className="border-b border-line">
                    {['Generator', 'Valid: raw', 'selected', 'final', 'Correct: raw', 'selected', 'final', 'Time / question'].map((h, i) => (
                      <th key={i} className="px-4 py-2 font-medium">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {generators.map((g) => {
                    const e = r.nl2sql_by_generator[g]
                    return (
                      <tr key={g} className="border-b border-line last:border-0">
                        <td className="px-4 py-2 font-medium">{g}</td>
                        {[e.raw_validity, e.selected_validity, e.final_validity, e.raw_execution_accuracy, e.selected_execution_accuracy, e.final_execution_accuracy].map((v, i) => (
                          <td key={i} className="px-4 py-2 tabular-nums">{pct(v)}</td>
                        ))}
                        <td className="px-4 py-2 tabular-nums">{ms(e.mean_generation_ms)}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}

      {r.figures.length > 0 && (
        <Card>
          <CardHeader icon={<ImageIcon className="size-4" />} title="Report figures" subtitle="As generated by make evaluate (reports/figures)" />
          <div className="grid gap-4 p-5 md:grid-cols-2 xl:grid-cols-3">
            {r.figures.map((f) => (
              <figure key={f} className="overflow-hidden rounded-lg border border-line bg-white">
                <a href={api.figureUrl(f)} target="_blank" rel="noreferrer">
                  <img src={api.figureUrl(f)} alt={FIGURE_CAPTIONS[f] ?? f} loading="lazy" className="aspect-[4/3] w-full object-contain p-2" />
                </a>
                <figcaption className="border-t border-line bg-surface px-3 py-2 text-xs text-ink-2">{FIGURE_CAPTIONS[f] ?? f}</figcaption>
              </figure>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}

export default function ResultsPage() {
  const results = useQuery({ queryKey: ['results'], queryFn: api.results, staleTime: 10 * 60_000 })
  return (
    <>
      <PageHeader title="Research results" description="How well SQLDiagnose works, measured on held-out data. Regenerate with make evaluate." />
      {results.isLoading ? (
        <div className="grid gap-3 sm:grid-cols-4">{[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-24" />)}</div>
      ) : results.error ? (
        (results.error as { status?: number }).status === 404 ? (
          <Card>
            <EmptyState icon={<FlaskConical className="size-5" />} title="No evaluation results on this server">
              Run <code className="font-mono">make evaluate</code> to produce reports/results.json.
            </EmptyState>
          </Card>
        ) : (
          <Callout tone="critical">{(results.error as Error).message}</Callout>
        )
      ) : (
        <Body r={results.data!} />
      )}
    </>
  )
}
