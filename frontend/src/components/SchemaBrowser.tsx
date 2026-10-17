import { ChevronRight, KeyRound, Link2, Lock, LockOpen, Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import type { AccessPolicy, DatabaseSchema } from '../lib/types'
import { IconButton, Input } from './ui'
import { cx } from '../lib/cx'

interface Props {
  schema: DatabaseSchema
  policy?: AccessPolicy
  onPolicyChange?: (p: AccessPolicy) => void
  onInsert?: (text: string) => void
  defaultOpen?: boolean
  compact?: boolean
}

/** Tables and columns of a schema; optional restriction toggles (access policy) and click-to-insert. */
export default function SchemaBrowser({ schema, policy, onPolicyChange, onInsert, defaultOpen = false, compact }: Props) {
  const tables = Object.keys(schema)
  const [open, setOpen] = useState<Record<string, boolean>>(() => (defaultOpen || tables.length <= 3 ? Object.fromEntries(tables.map((t) => [t, true])) : {}))
  const [filter, setFilter] = useState('')
  const term = filter.trim().toLowerCase()

  const visible = useMemo(
    () =>
      tables.filter(
        (t) => !term || t.toLowerCase().includes(term) || Object.keys(schema[t].columns ?? {}).some((c) => c.toLowerCase().includes(term)),
      ),
    [tables, schema, term],
  )

  const lower = (xs: string[] = []) => new Set(xs.map((x) => x.toLowerCase()))
  const rTables = lower(policy?.restricted_tables)
  const rCols = lower(policy?.restricted_columns)

  const toggleTable = (t: string) => {
    if (!policy || !onPolicyChange) return
    const has = rTables.has(t.toLowerCase())
    onPolicyChange({
      ...policy,
      restricted_tables: has ? policy.restricted_tables.filter((x) => x.toLowerCase() !== t.toLowerCase()) : [...policy.restricted_tables, t],
    })
  }
  const toggleColumn = (t: string, c: string) => {
    if (!policy || !onPolicyChange) return
    const key = `${t}.${c}`
    const has = rCols.has(key.toLowerCase())
    onPolicyChange({
      ...policy,
      restricted_columns: has ? policy.restricted_columns.filter((x) => x.toLowerCase() !== key.toLowerCase()) : [...policy.restricted_columns, key],
    })
  }

  return (
    <div>
      {tables.length > 4 && (
        <div className="relative mb-2">
          <Search className="pointer-events-none absolute top-2.5 left-2.5 size-4 text-ink-muted" />
          <Input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Find a table or column" className="h-8 pl-8 text-[13px]" aria-label="Find a table or column" />
        </div>
      )}
      <ul className="space-y-0.5">
        {visible.map((t) => {
          const info = schema[t]
          const isOpen = open[t] || !!term
          const locked = rTables.has(t.toLowerCase())
          const fks = new Map((info.foreign_keys ?? []).map((f) => [f.column.toLowerCase(), `${f.target_table}.${f.target_column}`]))
          const pks = lower(info.primary_keys)
          return (
            <li key={t}>
              <div className="group flex items-center gap-1 rounded-md hover:bg-surface-2">
                <button type="button" onClick={() => setOpen((o) => ({ ...o, [t]: !isOpen }))} aria-expanded={isOpen} className="flex min-w-0 flex-1 items-center gap-1.5 px-1.5 py-1 text-left">
                  <ChevronRight className={cx('size-3.5 shrink-0 text-ink-muted transition-transform', isOpen && 'rotate-90')} />
                  <span className={cx('truncate font-mono text-[13px] font-medium', locked ? 'text-critical-text line-through decoration-1' : 'text-ink')}>{t}</span>
                  <span className="shrink-0 text-[11px] text-ink-muted">{Object.keys(info.columns ?? {}).length}</span>
                </button>
                {onInsert && (
                  <button type="button" onClick={() => onInsert(t)} className="hidden rounded px-1.5 py-0.5 text-[11px] text-accent-text group-hover:block hover:bg-accent-soft">
                    insert
                  </button>
                )}
                {onPolicyChange && (
                  <IconButton label={locked ? `Allow table ${t}` : `Restrict table ${t}`} onClick={() => toggleTable(t)} className={cx('size-7', locked ? 'text-critical-text' : 'opacity-0 group-hover:opacity-100 focus:opacity-100')}>
                    {locked ? <Lock className="size-3.5" /> : <LockOpen className="size-3.5" />}
                  </IconButton>
                )}
              </div>
              {isOpen && (
                <ul className={cx('mb-1 ml-[19px] border-l border-line pl-2', compact ? 'space-y-0' : 'space-y-px')}>
                  {Object.entries(info.columns ?? {}).map(([c, type]) => {
                    const colLocked = rCols.has(`${t}.${c}`.toLowerCase())
                    const fk = fks.get(c.toLowerCase())
                    return (
                      <li key={c} className="group/col flex items-center gap-1.5 rounded px-1.5 py-[3px] text-[13px] hover:bg-surface-2">
                        {pks.has(c.toLowerCase()) ? <KeyRound className="size-3 shrink-0 text-[color:var(--cat-4)]" aria-label="primary key" /> : fk ? <Link2 className="size-3 shrink-0 text-ink-muted" aria-label="foreign key" /> : <span className="size-3 shrink-0" />}
                        <button
                          type="button"
                          disabled={!onInsert}
                          onClick={() => onInsert?.(c)}
                          className={cx('min-w-0 truncate text-left font-mono disabled:cursor-default', colLocked ? 'text-critical-text line-through' : 'text-ink', onInsert && 'hover:text-accent-text')}
                          title={fk ? `${c} → ${fk}` : onInsert ? `Insert ${c}` : c}
                        >
                          {c}
                        </button>
                        <span className="ml-auto shrink-0 font-mono text-[11px] text-ink-muted uppercase">{type || 'any'}</span>
                        {onPolicyChange && (
                          <IconButton label={colLocked ? `Allow column ${t}.${c}` : `Restrict column ${t}.${c}`} onClick={() => toggleColumn(t, c)} className={cx('size-6', colLocked ? 'text-critical-text' : 'opacity-0 group-hover/col:opacity-100 focus:opacity-100')}>
                            {colLocked ? <Lock className="size-3" /> : <LockOpen className="size-3" />}
                          </IconButton>
                        )}
                      </li>
                    )
                  })}
                </ul>
              )}
            </li>
          )
        })}
      </ul>
      {visible.length === 0 && <p className="px-2 py-3 text-sm text-ink-muted">Nothing matches “{filter}”.</p>}
    </div>
  )
}
