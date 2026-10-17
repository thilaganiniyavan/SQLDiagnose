import { Ban, Database, FolderOpen, HardDrive, Plus, Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { relativeTime } from '../lib/format'
import { useDatabases, useSavedSchemas } from '../lib/queries'
import { useDatabase, type Selection } from '../state/database'
import { Button, Dialog, EmptyState, Input, Pill, Segmented, Skeleton } from './ui'
import { cx } from '../lib/cx'

type Tab = 'saved' | 'examples'

export default function DatabasePicker({ open, onClose }: { open: boolean; onClose: () => void }) {
  const db = useDatabase()
  const saved = useSavedSchemas()
  const examples = useDatabases()
  const [tab, setTab] = useState<Tab>(db.selection.kind === 'saved' ? 'saved' : 'examples')
  const [search, setSearch] = useState('')

  const choose = (s: Selection) => {
    db.select(s)
    onClose()
  }
  const term = search.trim().toLowerCase()
  const filteredExamples = useMemo(() => (examples.data ?? []).filter((d) => d.db_id.toLowerCase().includes(term)), [examples.data, term])
  const filteredSaved = useMemo(() => (saved.data ?? []).filter((d) => d.name.toLowerCase().includes(term)), [saved.data, term])

  const isActive = (s: Selection) => JSON.stringify(s) === JSON.stringify(db.selection)
  // mark databases with data only when it differs between them
  const mixedData = !!examples.data && examples.data.some((d) => d.executable) && examples.data.some((d) => !d.executable)
  const rowClass = (active: boolean) =>
    cx(
      'flex w-full items-center gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors',
      active ? 'border-accent bg-accent-soft' : 'border-transparent hover:bg-surface-2',
    )

  return (
    <Dialog open={open} onClose={onClose} title="Choose a database" description="Queries are checked against this schema. Everything stays selected across pages." wide>
      <div className="flex flex-wrap items-center gap-3">
        <Segmented<Tab>
          label="Source"
          value={tab}
          onChange={setTab}
          options={[
            { value: 'examples', label: `Examples${examples.data ? ` (${examples.data.length})` : ''}`, icon: <Database className="size-3.5" /> },
            { value: 'saved', label: `My schemas${saved.data ? ` (${saved.data.length})` : ''}`, icon: <FolderOpen className="size-3.5" /> },
          ]}
        />
        <div className="relative min-w-48 flex-1">
          <Search className="pointer-events-none absolute top-2.5 left-2.5 size-4 text-ink-muted" />
          <Input autoFocus value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Filter by name…" className="pl-8" aria-label="Filter databases" />
        </div>
      </div>

      <div className="mt-4 space-y-1">
        <button type="button" className={rowClass(db.selection.kind === 'none')} onClick={() => choose({ kind: 'none' })}>
          <Ban className="size-4 text-ink-muted" />
          <span className="flex-1">
            <span className="block text-sm font-medium">No schema</span>
            <span className="block text-xs text-ink-muted">Only grammar and schema-independent rules are checked.</span>
          </span>
        </button>

        {tab === 'examples' &&
          (examples.isLoading ? (
            Array.from({ length: 5 }, (_, i) => <Skeleton key={i} className="h-12" />)
          ) : filteredExamples.length === 0 ? (
            <EmptyState title="No example database matches" />
          ) : (
            <div className="grid gap-1 sm:grid-cols-2">
              {filteredExamples.map((d) => {
                const s: Selection = { kind: 'example', dbId: d.db_id }
                return (
                  <button key={d.db_id} type="button" className={rowClass(isActive(s))} onClick={() => choose(s)}>
                    <Database className="size-4 shrink-0 text-ink-muted" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-mono text-[13px] font-medium">{d.db_id}</span>
                      <span className="block text-xs text-ink-muted">
                        {d.tables} tables · {d.columns} columns
                      </span>
                    </span>
                    {mixedData && d.executable && (
                      <Pill tone="accent" title="Real data available: queries can be run">
                        data
                      </Pill>
                    )}
                  </button>
                )
              })}
            </div>
          ))}

        {tab === 'saved' &&
          (saved.isLoading ? (
            <Skeleton className="h-12" />
          ) : filteredSaved.length === 0 ? (
            <EmptyState icon={<HardDrive className="size-5" />} title={term ? 'No saved schema matches' : 'No saved schemas yet'} action={<Link to="/schemas" onClick={onClose}><Button variant="primary" icon={<Plus className="size-4" />}>Import a schema</Button></Link>}>
              Import your own schema from CREATE TABLE statements, a SQLite file or a live database.
            </EmptyState>
          ) : (
            filteredSaved.map((d) => {
              const s: Selection = { kind: 'saved', id: d.id, name: d.name }
              return (
                <button key={d.id} type="button" className={rowClass(db.selection.kind === 'saved' && db.selection.id === d.id)} onClick={() => choose(s)}>
                  <FolderOpen className="size-4 shrink-0 text-ink-muted" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">{d.name}</span>
                    <span className="block text-xs text-ink-muted">
                      {d.tables} tables · {d.columns} columns · from {d.source} · {relativeTime(d.updated_at)}
                    </span>
                  </span>
                  {d.executable && <Pill tone="accent">data</Pill>}
                </button>
              )
            })
          ))}
      </div>
      <p className="mt-4 text-xs text-ink-muted">
        {tab === 'examples' && examples.data?.every((d) => d.executable) && 'Every example database includes its data, so queries can be run. '}
        Need your own schema?{' '}
        <Link to="/schemas" onClick={onClose} className="font-medium text-accent-text hover:underline">
          Import one on the Schemas page
        </Link>
        .
      </p>
    </Dialog>
  )
}
