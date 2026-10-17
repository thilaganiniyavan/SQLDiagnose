import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Braces, Check, Code2, Database, Download, FileUp, FolderOpen, Pencil, Plug, Search, Trash2, Upload, X } from 'lucide-react'
import { useMemo, useRef, useState, type DragEvent } from 'react'
import { toast } from 'sonner'
import SchemaBrowser from '../components/SchemaBrowser'
import SqlBlock from '../components/SqlBlock'
import { Button, Callout, Card, CardHeader, Confirm, CopyButton, EmptyState, Field, IconButton, Input, PageHeader, Pill, Segmented, Select, Skeleton, Switch, Textarea } from '../components/ui'
import { cx } from '../lib/cx'
import { api } from '../lib/api'
import { download } from '../lib/csv'
import { relativeTime } from '../lib/format'
import { useDatabases, useHealth, useSavedSchemas } from '../lib/queries'
import type { DatabaseSchema, SavedSchemaSummary } from '../lib/types'
import { useDatabase } from '../state/database'
import { useSessionState } from '../state/session'

type Method = 'ddl' | 'sqlite' | 'live' | 'json'
const DIALECTS = ['sqlite', 'postgres', 'mysql', 'tsql', 'oracle', 'snowflake', 'bigquery']
const SAMPLE_DDL = `CREATE TABLE customers (
  id INT PRIMARY KEY,
  name VARCHAR(80) NOT NULL,
  country VARCHAR(40),
  signup_date DATE
);
CREATE TABLE orders (
  id INT PRIMARY KEY,
  customer_id INT REFERENCES customers(id),
  total DECIMAL(10, 2),
  status VARCHAR(20)
);`
const SAMPLE_JSON = JSON.stringify(
  {
    users: { columns: { id: 'INTEGER', name: 'TEXT', age: 'INTEGER' }, primary_keys: ['id'] },
    orders: {
      columns: { id: 'INTEGER', user_id: 'INTEGER', total: 'REAL' },
      primary_keys: ['id'],
      foreign_keys: [{ column: 'user_id', target_table: 'users', target_column: 'id' }],
    },
  },
  null,
  2,
)

interface Draft {
  schema: DatabaseSchema
  source: Method
  name: string
}

// ------------------------------------------------------------------ import
function ImportCard() {
  const db = useDatabase()
  const qc = useQueryClient()
  const health = useHealth()
  const [method, setMethod] = useSessionState<Method>('schemas.method', 'ddl')
  const [ddl, setDdl] = useSessionState('schemas.ddl', SAMPLE_DDL)
  const [dialect, setDialect] = useSessionState('schemas.dialect', 'postgres')
  const [json, setJson] = useSessionState('schemas.json', SAMPLE_JSON)
  const [engine, setEngine] = useState<'postgresql' | 'mysql'>('postgresql')
  const [dsn, setDsn] = useState('dbname=mydb user=postgres host=localhost port=5432')
  const [mysql, setMysql] = useState({ host: 'localhost', port: '3306', user: 'root', password: '', database: '' })
  const [file, setFile] = useState<File | null>(null)
  const [keepData, setKeepData] = useState(true)
  const [sqliteName, setSqliteName] = useState('')
  const [draft, setDraft] = useState<Draft | null>(null)
  const [dragging, setDragging] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)

  const parse = useMutation({
    mutationFn: async (): Promise<Draft> => {
      if (method === 'ddl') {
        const r = await api.parseDdl(ddl, dialect)
        return { schema: r.database_schema, source: 'ddl', name: `${Object.keys(r.database_schema)[0] ?? 'my'} schema` }
      }
      if (method === 'json') {
        let parsed: unknown
        try {
          parsed = JSON.parse(json)
        } catch (e) {
          throw new Error(`Invalid JSON: ${(e as Error).message}`, { cause: e })
        }
        if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed) || !Object.keys(parsed).length) throw new Error('The JSON must be an object of tables.')
        return { schema: parsed as DatabaseSchema, source: 'json', name: 'My schema' }
      }
      const conn = engine === 'postgresql' ? { dsn } : { ...mysql, port: Number(mysql.port) || 3306 }
      const r = await api.parseLive(engine, conn)
      return { schema: r.database_schema, source: 'live', name: engine === 'postgresql' ? (dsn.match(/dbname=(\S+)/)?.[1] ?? 'database') : mysql.database || 'database' }
    },
    onSuccess: setDraft,
    onError: (e) => toast.error(e.message),
  })

  const saveDraft = useMutation({
    mutationFn: (d: Draft) => api.createSavedSchema({ name: d.name.trim() || 'My schema', source: d.source, database_schema: d.schema }),
    onSuccess: (s) => {
      qc.invalidateQueries({ queryKey: ['saved-schemas'] })
      db.select({ kind: 'saved', id: s.id, name: s.name })
      setDraft(null)
      toast.success(`Saved “${s.name}” and selected it`)
    },
    onError: (e) => toast.error(e.message),
  })

  const uploadSqlite = useMutation({
    mutationFn: () => api.uploadSqlite(file!, sqliteName.trim(), keepData),
    onSuccess: (s) => {
      qc.invalidateQueries({ queryKey: ['saved-schemas'] })
      db.select({ kind: 'saved', id: s.id, name: s.name })
      setFile(null)
      setSqliteName('')
      toast.success(`Imported “${s.name}” (${s.tables} tables) and selected it${s.executable ? '; queries can be run on its data' : ''}`)
    },
    onError: (e) => toast.error(e.message),
  })

  const pick = (f?: File) => {
    if (!f) return
    setFile(f)
    setSqliteName(f.name.replace(/\.(sqlite3?|db)$/i, ''))
  }
  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setDragging(false)
    pick(e.dataTransfer.files?.[0])
  }

  const liveDisabled = health.data && !health.data.live_schema_enabled

  return (
    <Card>
      <CardHeader title="Import a schema" subtitle="Bring your own database structure. It is saved in your workspace and can be selected from the database menu." />
      <div className="space-y-4 p-5">
        <Segmented<Method>
          label="Import from"
          value={method}
          onChange={(m) => {
            setMethod(m)
            setDraft(null)
          }}
          options={[
            { value: 'ddl', label: 'CREATE TABLE', icon: <Code2 className="size-3.5" /> },
            { value: 'sqlite', label: 'SQLite file', icon: <FileUp className="size-3.5" /> },
            { value: 'live', label: 'Live database', icon: <Plug className="size-3.5" /> },
            { value: 'json', label: 'JSON', icon: <Braces className="size-3.5" /> },
          ]}
        />

        {method === 'ddl' && (
          <div className="space-y-3">
            <Field label="Dialect" htmlFor="dialect" hint="Statements are converted to SQLite to read the structure; declared types are kept.">
              <Select id="dialect" value={dialect} onChange={(e) => setDialect(e.target.value)} className="max-w-xs">
                {DIALECTS.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="CREATE TABLE statements" htmlFor="ddl">
              <Textarea id="ddl" value={ddl} onChange={(e) => setDdl(e.target.value)} rows={10} spellCheck={false} className="font-mono text-[13px]" />
            </Field>
          </div>
        )}

        {method === 'json' && (
          <Field
            label="Schema JSON"
            htmlFor="json"
            hint={<>Format: <code className="font-mono">{'{"table": {"columns": {"col": "TYPE"}, "primary_keys": [...], "foreign_keys": [...]}}'}</code></>}
          >
            <Textarea id="json" value={json} onChange={(e) => setJson(e.target.value)} rows={12} spellCheck={false} className="font-mono text-[13px]" />
          </Field>
        )}

        {method === 'sqlite' && (
          <div className="space-y-4">
            <div
              onDragOver={(e) => {
                e.preventDefault()
                setDragging(true)
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
              className={cx('flex flex-col items-center rounded-xl border-2 border-dashed px-6 py-8 text-center', dragging ? 'border-accent bg-accent-soft' : 'border-line-strong')}
            >
              <Upload className="mb-2 size-6 text-ink-muted" />
              {file ? (
                <p className="flex items-center gap-2 text-sm">
                  <Database className="size-4 text-accent-text" />
                  <b>{file.name}</b> <span className="text-xs text-ink-muted">{(file.size / 1024 / 1024).toFixed(2)} MB</span>
                  <IconButton label="Remove file" className="size-6" onClick={() => setFile(null)}>
                    <X className="size-3.5" />
                  </IconButton>
                </p>
              ) : (
                <p className="text-sm text-ink-2">Drop a .sqlite / .db file here, or</p>
              )}
              <Button size="sm" className="mt-3" onClick={() => fileInput.current?.click()}>
                {file ? 'Choose another file' : 'Choose file'}
              </Button>
              <input ref={fileInput} type="file" accept=".sqlite,.sqlite3,.db,application/x-sqlite3,application/octet-stream" className="hidden" onChange={(e) => { pick(e.target.files?.[0]); e.target.value = '' }} />
            </div>
            {file && (
              <Field label="Name" htmlFor="sqlite-name">
                <Input id="sqlite-name" value={sqliteName} onChange={(e) => setSqliteName(e.target.value)} maxLength={120} />
              </Field>
            )}
            <Switch checked={keepData} onChange={setKeepData} label="Keep the data so queries can be run" description="The file is stored in your workspace on the server; queries run read-only." />
          </div>
        )}

        {method === 'live' && (
          <div className="space-y-3">
            {liveDisabled && <Callout tone="warning" title="Disabled on this server">Live introspection is turned off (api.enable_live_schema_parsing).</Callout>}
            <Segmented<'postgresql' | 'mysql'>
              label="Engine"
              value={engine}
              onChange={setEngine}
              options={[
                { value: 'postgresql', label: 'PostgreSQL' },
                { value: 'mysql', label: 'MySQL' },
              ]}
            />
            {engine === 'postgresql' ? (
              <Field label="Connection string" htmlFor="dsn" hint="libpq format, e.g. dbname=shop user=postgres host=localhost port=5432 password=…">
                <Input id="dsn" value={dsn} onChange={(e) => setDsn(e.target.value)} className="font-mono text-[13px]" autoComplete="off" />
              </Field>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2">
                {(['host', 'port', 'user', 'password', 'database'] as const).map((k) => (
                  <Field key={k} label={k[0].toUpperCase() + k.slice(1)} htmlFor={`my-${k}`}>
                    <Input id={`my-${k}`} type={k === 'password' ? 'password' : 'text'} value={mysql[k]} onChange={(e) => setMysql({ ...mysql, [k]: e.target.value })} autoComplete="off" />
                  </Field>
                ))}
              </div>
            )}
            <p className="text-xs text-ink-muted">Credentials are used for this one request to read the table structure and are never stored. Only the schema is saved.</p>
          </div>
        )}

        <div className="flex justify-end border-t border-line pt-4">
          {method === 'sqlite' ? (
            <Button variant="primary" icon={<Upload className="size-4" />} disabled={!file} loading={uploadSqlite.isPending} onClick={() => uploadSqlite.mutate()}>
              Import and use
            </Button>
          ) : (
            <Button variant="primary" onClick={() => parse.mutate()} loading={parse.isPending} disabled={method === 'live' && !!liveDisabled}>
              {method === 'live' ? 'Connect and read schema' : 'Read schema'}
            </Button>
          )}
        </div>

        {draft && (
          <div className="space-y-3 rounded-xl border border-accent bg-accent-soft/40 p-4">
            <div className="flex items-center gap-2 text-sm font-medium">
              <Check className="size-4 text-good-text" />
              Found {Object.keys(draft.schema).length} table{Object.keys(draft.schema).length === 1 ? '' : 's'} — check them, name the schema and save.
            </div>
            <div className="scrollbar-thin max-h-72 overflow-y-auto rounded-lg border border-line bg-surface p-2">
              <SchemaBrowser schema={draft.schema} defaultOpen />
            </div>
            <div className="flex flex-wrap items-end gap-2">
              <Field label="Name" htmlFor="draft-name" className="min-w-56 flex-1">
                <Input id="draft-name" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} maxLength={120} />
              </Field>
              <Button onClick={() => setDraft(null)}>Discard</Button>
              <Button variant="primary" loading={saveDraft.isPending} onClick={() => saveDraft.mutate(draft)} disabled={!draft.name.trim()}>
                Save and use
              </Button>
            </div>
          </div>
        )}
      </div>
    </Card>
  )
}

// ------------------------------------------------------------------ saved schemas
function SavedItem({ s }: { s: SavedSchemaSummary }) {
  const db = useDatabase()
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [renaming, setRenaming] = useState(false)
  const [name, setName] = useState(s.name)
  const [confirm, setConfirm] = useState(false)
  const active = db.selection.kind === 'saved' && db.selection.id === s.id
  const detail = useQuery({ queryKey: ['saved-schema', s.id], queryFn: () => api.savedSchema(s.id), enabled: open })

  const rename = useMutation({
    mutationFn: () => api.updateSavedSchema(s.id, { name: name.trim() }),
    onSuccess: (u) => {
      qc.invalidateQueries({ queryKey: ['saved-schemas'] })
      qc.setQueryData(['saved-schema', s.id], (old: object | undefined) => ({ ...old, ...u }))
      if (active) db.select({ kind: 'saved', id: u.id, name: u.name })
      setRenaming(false)
    },
    onError: (e) => toast.error(e.message),
  })
  const remove = useMutation({
    mutationFn: () => api.deleteSavedSchema(s.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['saved-schemas'] })
      if (active) db.select({ kind: 'example', dbId: 'concert_singer' })
      toast.success(`Deleted “${s.name}”`)
      setConfirm(false)
    },
    onError: (e) => toast.error(e.message),
  })

  return (
    <li className={cx('rounded-lg border', active ? 'border-accent' : 'border-line')}>
      <div className="flex flex-wrap items-center gap-3 px-3 py-2.5">
        <FolderOpen className="size-4 shrink-0 text-ink-muted" />
        <div className="min-w-0 flex-1">
          {renaming ? (
            <form
              className="flex items-center gap-1.5"
              onSubmit={(e) => {
                e.preventDefault()
                if (name.trim()) rename.mutate()
              }}
            >
              <Input autoFocus value={name} onChange={(e) => setName(e.target.value)} className="h-7 text-sm" maxLength={120} aria-label="New name" />
              <IconButton label="Save name" type="submit" disabled={!name.trim()}>
                <Check className="size-4" />
              </IconButton>
              <IconButton label="Cancel" onClick={() => { setRenaming(false); setName(s.name) }}>
                <X className="size-4" />
              </IconButton>
            </form>
          ) : (
            <button type="button" className="block max-w-full truncate text-left text-sm font-medium hover:underline" onClick={() => setOpen(!open)} aria-expanded={open}>
              {s.name}
            </button>
          )}
          <p className="text-xs text-ink-muted">
            {s.tables} tables · {s.columns} columns · from {s.source} · updated {relativeTime(s.updated_at)}
          </p>
        </div>
        <div className="flex items-center gap-1">
          {s.executable && <Pill tone="accent" title="Queries can be run on this data">data</Pill>}
          {s.access_policy && (s.access_policy.restricted_tables.length + s.access_policy.restricted_columns.length > 0) && <Pill tone="critical">restricted</Pill>}
          {active ? (
            <Pill tone="good"><Check className="size-3" />in use</Pill>
          ) : (
            <Button size="sm" variant="primary" onClick={() => { db.select({ kind: 'saved', id: s.id, name: s.name }); toast.success(`Using “${s.name}”`) }}>
              Use
            </Button>
          )}
          <IconButton label="Rename" onClick={() => setRenaming(true)}>
            <Pencil className="size-3.5" />
          </IconButton>
          <IconButton label="Delete" onClick={() => setConfirm(true)} className="hover:text-critical-text">
            <Trash2 className="size-3.5" />
          </IconButton>
        </div>
      </div>
      {open && (
        <div className="space-y-3 border-t border-line px-3 py-3">
          {detail.isLoading ? (
            <Skeleton className="h-24" />
          ) : detail.data ? (
            <>
              <div className="scrollbar-thin max-h-72 overflow-y-auto">
                <SchemaBrowser schema={detail.data.database_schema} />
              </div>
              <div className="flex flex-wrap gap-1.5">
                {detail.data.ddl && <CopyButton text={detail.data.ddl} label="Copy DDL" variant="secondary" />}
                <Button size="sm" icon={<Download className="size-3.5" />} onClick={() => download(`${s.name}.json`, JSON.stringify(detail.data!.database_schema, null, 2), 'application/json')}>
                  Export JSON
                </Button>
              </div>
            </>
          ) : (
            <Callout tone="critical">{(detail.error as Error)?.message}</Callout>
          )}
        </div>
      )}
      <Confirm open={confirm} onClose={() => setConfirm(false)} onConfirm={() => remove.mutate()} busy={remove.isPending} title={`Delete “${s.name}”?`}>
        The schema{s.executable ? ' and its stored database file' : ''} will be removed from your workspace. History entries that used it can no longer be re-run.
      </Confirm>
    </li>
  )
}

function SavedCard() {
  const saved = useSavedSchemas()
  return (
    <Card>
      <CardHeader title="Your schemas" subtitle="Saved in this browser’s workspace on the server." />
      <div className="p-3">
        {saved.isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-14" />
            <Skeleton className="h-14" />
          </div>
        ) : saved.error ? (
          <Callout tone="critical">{(saved.error as Error).message}</Callout>
        ) : !saved.data?.length ? (
          <EmptyState icon={<FolderOpen className="size-5" />} title="No saved schemas yet">
            Import one with the form — from CREATE TABLE statements, a SQLite file, a live database or JSON.
          </EmptyState>
        ) : (
          <ul className="space-y-2">
            {saved.data.map((s) => (
              <SavedItem key={s.id} s={s} />
            ))}
          </ul>
        )}
      </div>
    </Card>
  )
}

// ------------------------------------------------------------------ examples
function ExamplesCard() {
  const db = useDatabase()
  const dbs = useDatabases()
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<string | null>(null)
  const detail = useQuery({ queryKey: ['example-schema', selected], queryFn: () => api.exampleSchema(selected!), enabled: !!selected, staleTime: Infinity })
  const list = useMemo(() => (dbs.data ?? []).filter((d) => d.db_id.includes(search.trim().toLowerCase())), [dbs.data, search])

  return (
    <Card>
      <CardHeader title="Example databases" subtitle={`${dbs.data?.length ?? '…'} databases from the Spider benchmark, ready to use.`} />
      <div className="grid gap-0 lg:grid-cols-[280px_minmax(0,1fr)]">
        <div className="border-b border-line p-3 lg:border-r lg:border-b-0">
          <div className="relative mb-2">
            <Search className="pointer-events-none absolute top-2.5 left-2.5 size-4 text-ink-muted" />
            <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Filter" className="h-8 pl-8 text-[13px]" aria-label="Filter example databases" />
          </div>
          <ul className="scrollbar-thin max-h-96 space-y-px overflow-y-auto">
            {list.map((d) => (
              <li key={d.db_id}>
                <button
                  type="button"
                  onClick={() => setSelected(d.db_id)}
                  className={cx('flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left font-mono text-[13px]', selected === d.db_id ? 'bg-accent-soft text-ink' : 'text-ink-2 hover:bg-surface-2')}
                >
                  <span className="truncate">{d.db_id}</span>
                  <span className="shrink-0 font-sans text-[11px] text-ink-muted">{d.tables}t</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
        <div className="min-w-0 p-4">
          {!selected ? (
            <EmptyState icon={<Database className="size-5" />} title="Pick a database to see its tables" />
          ) : detail.isLoading ? (
            <Skeleton className="h-40" />
          ) : detail.data ? (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="font-mono text-[15px] font-semibold">{selected}</h3>
                <div className="flex items-center gap-1.5">
                  {detail.data.executable && <Pill tone="accent">data</Pill>}
                  {db.selection.kind === 'example' && db.selection.dbId === selected ? (
                    <Pill tone="good"><Check className="size-3" />in use</Pill>
                  ) : (
                    <Button size="sm" variant="primary" onClick={() => { db.select({ kind: 'example', dbId: selected }); toast.success(`Using ${selected}`) }}>
                      Use this database
                    </Button>
                  )}
                </div>
              </div>
              <div className="grid gap-4 2xl:grid-cols-2">
                <div className="scrollbar-thin max-h-96 overflow-y-auto">
                  <SchemaBrowser schema={detail.data.database_schema} />
                </div>
                <div className="scrollbar-thin max-h-96 overflow-y-auto">
                  <SqlBlock sql={detail.data.ddl} actions={<CopyButton text={detail.data.ddl} label="Copy DDL" />} />
                </div>
              </div>
            </div>
          ) : (
            <Callout tone="critical">{(detail.error as Error)?.message}</Callout>
          )}
        </div>
      </div>
    </Card>
  )
}

export default function SchemasPage() {
  return (
    <>
      <PageHeader title="Schemas" description="Every check runs against a schema. Use one of the example databases, or import your own." />
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        <ImportCard />
        <SavedCard />
      </div>
      <div className="mt-6">
        <ExamplesCard />
      </div>
    </>
  )
}
