import { Fragment, type ReactNode } from 'react'
import { cx } from '../lib/cx'

const KEYWORDS = new Set(
  ('select from where group by order having limit offset join inner left right outer full cross on as and or not in is null ' +
    'like between exists distinct union all intersect except case when then else end asc desc with insert update delete into values set ' +
    'create table primary key foreign references cast count sum avg min max natural using recursive').split(' '),
)

/** Tiny SQL highlighter for read-only display (keywords, strings, numbers). */
function highlightSql(text: string): ReactNode[] {
  const out: ReactNode[] = []
  const re = /('(?:[^']|'')*'?|"(?:[^"]|"")*"?|`[^`]*`?|\b\d+(?:\.\d+)?\b|[A-Za-z_][A-Za-z0-9_]*|\s+|.)/g
  let m: RegExpExecArray | null
  let i = 0
  while ((m = re.exec(text))) {
    const t = m[0]
    if (t[0] === "'") out.push(<span key={i++} className="text-[color:var(--syn-string)]">{t}</span>)
    else if (/^\d/.test(t)) out.push(<span key={i++} className="text-[color:var(--syn-number)]">{t}</span>)
    else if (KEYWORDS.has(t.toLowerCase())) out.push(<span key={i++} className="font-semibold text-accent-text">{t}</span>)
    else out.push(<Fragment key={i++}>{t}</Fragment>)
  }
  return out
}

export default function SqlBlock({ sql, className, actions }: { sql: string; className?: string; actions?: ReactNode }) {
  return (
    <div className={cx('group relative rounded-lg border border-line bg-surface-2 px-3.5 py-2.5', className)}>
      <code className="sql block text-ink">{highlightSql(sql)}</code>
      {actions && <div className="mt-2 flex flex-wrap gap-1.5">{actions}</div>}
    </div>
  )
}
