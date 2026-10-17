export const pct = (v: number | null | undefined, digits = 1) =>
  v === null || v === undefined || Number.isNaN(v) ? '—' : `${(v * 100).toFixed(digits)}%`

export function ms(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  if (v < 1) return '<1 ms'
  if (v < 1000) return `${Math.round(v)} ms`
  return `${(v / 1000).toFixed(v < 10_000 ? 1 : 0)} s`
}

export const int = (v: number) => v.toLocaleString('en-US')

export function relativeTime(epochSeconds: number, now = Date.now()): string {
  const diff = Math.max(0, now / 1000 - epochSeconds)
  if (diff < 45) return 'just now'
  if (diff < 3600) return `${Math.round(diff / 60)} min ago`
  if (diff < 86_400) return `${Math.round(diff / 3600)} h ago`
  if (diff < 7 * 86_400) return `${Math.round(diff / 86_400)} d ago`
  return new Date(epochSeconds * 1000).toLocaleDateString()
}

export function duration(seconds: number): string {
  if (seconds < 60) return `${Math.floor(seconds)} s`
  const m = Math.floor(seconds / 60)
  if (m < 60) return `${m} min ${Math.floor(seconds % 60)} s`
  return `${Math.floor(m / 60)} h ${m % 60} min`
}
