function cell(v: unknown): string {
  if (v === null || v === undefined) return ''
  const s = Array.isArray(v) ? v.join('; ') : typeof v === 'object' ? JSON.stringify(v) : String(v)
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

export function toCsv(rows: Record<string, unknown>[], columns?: string[]): string {
  const cols = columns ?? Array.from(new Set(rows.flatMap((r) => Object.keys(r))))
  return [cols.join(','), ...rows.map((r) => cols.map((c) => cell(r[c])).join(','))].join('\n') + '\n'
}

export function download(filename: string, content: string, type = 'text/csv') {
  const blob = new Blob([content], { type: `${type};charset=utf-8` })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

/** Splits pasted text into queries: one per line, or separated by ';' when the text spans lines per query. */
export function splitQueries(text: string, mode: 'lines' | 'semicolons'): string[] {
  if (mode === 'lines') return text.split(/\r?\n/).map((q) => q.trim()).filter(Boolean)
  const out: string[] = []
  let cur = ''
  let quote: string | null = null
  for (const ch of text) {
    if (quote) {
      if (ch === quote) quote = null
    } else if (ch === "'" || ch === '"' || ch === '`') {
      quote = ch
    } else if (ch === ';') {
      if (cur.trim()) out.push(cur.trim().replace(/\s+/g, ' '))
      cur = ''
      continue
    }
    cur += ch
  }
  if (cur.trim()) out.push(cur.trim().replace(/\s+/g, ' '))
  return out
}
