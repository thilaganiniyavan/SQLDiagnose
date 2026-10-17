import { useState, type ReactNode } from 'react'
import type { TokenScore } from '../lib/types'
import { cx } from '../lib/cx'

// Small, dependency-free charts in the app's tokens. Bars are thin (<= 12px) with a rounded
// data end and a square baseline; values are labelled at the bar tip; every mark has a tooltip.

export interface BarDatum {
  key: string
  label: ReactNode
  value: number
  display?: string
  emphasis?: boolean
  tooltip?: string
}

/** One series: horizontal bars sharing a baseline. `max` defaults to the largest value. */
export function BarList({ data, max, format = (v) => v.toLocaleString(), ariaLabel, labelWidth = '11rem' }: { data: BarDatum[]; max?: number; format?: (v: number) => string; ariaLabel: string; labelWidth?: string }) {
  const top = max ?? Math.max(1e-9, ...data.map((d) => d.value))
  return (
    <ul aria-label={ariaLabel} className="space-y-1">
      {data.map((d) => {
        const w = Math.max(0, Math.min(1, d.value / top))
        const text = d.display ?? format(d.value)
        return (
          <li
            key={d.key}
            title={d.tooltip ?? `${typeof d.label === 'string' ? d.label : d.key}: ${text}`}
            className="group grid items-center gap-3 rounded-md px-1.5 py-1 hover:bg-surface-2"
            style={{ gridTemplateColumns: `${labelWidth} 1fr` }}
          >
            <span className={cx('truncate text-[13px]', d.emphasis ? 'font-semibold text-ink' : 'text-ink-2')}>{d.label}</span>
            <span className="flex items-center gap-2">
              <span className="relative h-2.5 flex-1">
                <span className="absolute inset-y-0 left-0 w-full border-l border-[color:var(--grid)]" aria-hidden />
                <span
                  className="absolute inset-y-0 left-0 rounded-r-[4px] transition-[width] duration-500"
                  style={{ width: `${w * 100}%`, background: d.emphasis ? 'var(--accent)' : 'color-mix(in srgb, var(--accent) 55%, var(--surface))' }}
                />
              </span>
              <span className={cx('w-14 shrink-0 text-right text-xs tabular-nums', d.emphasis ? 'font-semibold text-ink' : 'text-ink-2')}>{text}</span>
            </span>
          </li>
        )
      })}
    </ul>
  )
}

export interface Series {
  key: string
  label: string
  color: string
}

/** Up to three series per category (the first three categorical slots stay distinguishable for all readers). */
export function GroupedBars({ categories, series, values, max = 1, format, ariaLabel, labelWidth = '10rem' }: {
  categories: { key: string; label: ReactNode }[]
  series: Series[]
  values: (category: string, series: string) => number | null | undefined
  max?: number
  format: (v: number) => string
  ariaLabel: string
  labelWidth?: string
}) {
  return (
    <figure aria-label={ariaLabel}>
      <Legend series={series} />
      <div className="mt-3 space-y-2.5">
        {categories.map((c) => (
          <div key={c.key} className="grid items-center gap-3" style={{ gridTemplateColumns: `${labelWidth} 1fr` }}>
            <span className="truncate text-[13px] text-ink-2">{c.label}</span>
            <div className="space-y-[2px] border-l border-[color:var(--grid)]">
              {series.map((s) => {
                const v = values(c.key, s.key)
                const label = v === null || v === undefined ? '—' : format(v)
                return (
                  <div key={s.key} className="group flex items-center gap-2 hover:bg-surface-2" title={`${typeof c.label === 'string' ? c.label : c.key} · ${s.label}: ${label}`}>
                    <span className="relative h-2.5 flex-1">
                      <span className="absolute inset-y-0 left-0 rounded-r-[4px]" style={{ width: `${Math.max(0, Math.min(1, (v ?? 0) / max)) * 100}%`, background: s.color }} />
                    </span>
                    <span className="w-12 shrink-0 text-right text-[11px] text-ink-2 tabular-nums">{label}</span>
                  </div>
                )
              })}
            </div>
          </div>
        ))}
      </div>
    </figure>
  )
}

export function Legend({ series }: { series: Series[] }) {
  if (series.length < 2) return null
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2">
      {series.map((s) => (
        <li key={s.key} className="inline-flex items-center gap-1.5">
          <span className="size-2.5 rounded-[3px]" style={{ background: s.color }} aria-hidden />
          {s.label}
        </li>
      ))}
    </ul>
  )
}

/** Confusion matrix: rows = true class, columns = predicted; one-hue sequential scale by row share. */
export function ConfusionMatrix({ labels, matrix, short }: { labels: string[]; matrix: number[][]; short: (l: string) => string }) {
  const [hover, setHover] = useState<[number, number] | null>(null)
  const steps = ['var(--seq-0)', 'var(--seq-1)', 'var(--seq-2)', 'var(--seq-3)', 'var(--seq-4)', 'var(--seq-5)']
  return (
    <div className="overflow-x-auto scrollbar-thin">
      <table className="border-separate border-spacing-[2px] text-xs" aria-label="Confusion matrix (rows: true class, columns: predicted class)">
        <thead>
          <tr>
            <th className="px-2 text-left text-[11px] font-normal text-ink-muted">true ↓ / predicted →</th>
            {labels.map((l, j) => (
              <th key={l} scope="col" className={cx('w-14 px-1 pb-1 text-center text-[11px] font-medium', hover?.[1] === j ? 'text-ink' : 'text-ink-muted')}>
                {short(l)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {matrix.map((row, i) => {
            const total = row.reduce((a, b) => a + b, 0) || 1
            return (
              <tr key={labels[i]}>
                <th scope="row" className={cx('pr-2 text-right text-[11px] font-medium whitespace-nowrap', hover?.[0] === i ? 'text-ink' : 'text-ink-muted')}>
                  {short(labels[i])}
                </th>
                {row.map((n, j) => {
                  const share = n / total
                  const step = n === 0 ? 0 : Math.min(5, 1 + Math.floor(share * 5))
                  return (
                    <td
                      key={j}
                      onMouseEnter={() => setHover([i, j])}
                      onMouseLeave={() => setHover(null)}
                      title={`True ${labels[i]} predicted as ${labels[j]}: ${n} of ${total} (${(share * 100).toFixed(1)}%)`}
                      className={cx('h-9 w-14 rounded-[3px] text-center tabular-nums', i === j && 'font-semibold')}
                      style={{ background: steps[step], color: step >= 3 ? '#ffffff' : 'var(--ink)' }}
                    >
                      {n}
                    </td>
                  )
                })}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

/** Token attributions: diverging scale — red pushes towards the predicted class, blue against it. */
export function TokenHeatmap({ tokens }: { tokens: TokenScore[] }) {
  const peak = Math.max(1e-9, ...tokens.map((t) => Math.abs(t.score)))
  return (
    <div>
      <div className="flex flex-wrap gap-[3px] font-mono text-[13px]">
        {tokens.map((t, i) => {
          const w = Math.abs(t.score) / peak
          const rgb = t.score >= 0 ? 'var(--diverge-pos)' : 'var(--diverge-neg)'
          return (
            <span
              key={i}
              title={`${t.token}: ${t.score >= 0 ? '+' : ''}${t.score.toFixed(4)}`}
              className="rounded-[4px] border border-line px-1.5 py-0.5 text-ink"
              style={{ background: `rgba(${rgb}, ${(0.06 + 0.6 * w).toFixed(3)})` }}
            >
              {t.token}
            </span>
          )
        })}
      </div>
      <div className="mt-3 flex items-center gap-2 text-[11px] text-ink-muted">
        <span>against</span>
        <span className="h-2 w-28 rounded-full" style={{ background: 'linear-gradient(90deg, rgba(var(--diverge-neg),.66), var(--seq-0), rgba(var(--diverge-pos),.66))' }} aria-hidden />
        <span>towards the predicted class</span>
      </div>
    </div>
  )
}
