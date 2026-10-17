import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowUpRight, FileStack, History as HistoryIcon, MessageSquareText, Search, Stethoscope, Trash2 } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import ClassBadge from '../components/ClassBadge'
import { Button, Callout, Card, Confirm, EmptyState, IconButton, Input, PageHeader, Pill, Segmented, Skeleton } from '../components/ui'
import { api } from '../lib/api'
import { relativeTime } from '../lib/format'
import { useSavedSchemas } from '../lib/queries'
import type { HistoryItem, HistoryKind, SchemaContextBody } from '../lib/types'

const PAGE = 30
const KIND: Record<HistoryKind, { label: string; icon: ReactNode; path: string }> = {
  analyze: { label: 'Diagnosis', icon: <Stethoscope className="size-4" />, path: '/' },
  nl2sql: { label: 'Question', icon: <MessageSquareText className="size-4" />, path: '/ask' },
  batch: { label: 'Batch', icon: <FileStack className="size-4" />, path: '/batch' },
}

function useDebounced<T>(value: T, delay = 300): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), delay)
    return () => clearTimeout(t)
  }, [value, delay])
  return v
}

function ContextLabel({ ctx, names }: { ctx: SchemaContextBody; names: Record<string, string> }) {
  const locks = (ctx.access_policy?.restricted_tables.length ?? 0) + (ctx.access_policy?.restricted_columns.length ?? 0)
  const label = ctx.db_id ? ctx.db_id : ctx.schema_id ? (names[ctx.schema_id] ?? 'deleted schema') : ctx.database_schema ? 'inline schema' : 'no schema'
  return (
    <span className="text-xs text-ink-muted">
      on <span className={ctx.db_id ? 'font-mono' : ''}>{label}</span>
      {locks > 0 && ` · ${locks} restricted`}
    </span>
  )
}

function Outcome({ item }: { item: HistoryItem }) {
  const s = item.summary as Record<string, unknown>
  if (item.kind === 'batch')
    return (
      <span className="text-xs text-ink-2 tabular-nums">
        {String(s.total)} queries · {String(s.errors)} errors · {String(s.repaired)} fixed
      </span>
    )
  if (item.kind === 'nl2sql') {
    const ok = s.status !== 'invalid' && s.status !== 'no_candidate'
    return <Pill tone={ok ? 'good' : 'critical'}>{String(s.status).replace('_', ' ')}</Pill>
  }
  return (
    <span className="flex flex-wrap items-center gap-1.5">
      <ClassBadge value={item.error_class} size="sm" />
      {s.repair_success === true && <Pill tone="good">fixed</Pill>}
      {s.repair_success === false && <Pill tone="warning">not fixed</Pill>}
    </span>
  )
}

export default function HistoryPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const saved = useSavedSchemas()
  const names = Object.fromEntries((saved.data ?? []).map((s) => [s.id, s.name]))
  const [kind, setKind] = useState<HistoryKind | 'all'>('all')
  const [search, setSearch] = useState('')
  const term = useDebounced(search.trim())
  const [confirmClear, setConfirmClear] = useState(false)

  const history = useInfiniteQuery({
    queryKey: ['history', kind, term],
    queryFn: ({ pageParam }) => api.history({ kind: kind === 'all' ? undefined : kind, search: term || undefined, limit: PAGE, offset: pageParam }),
    initialPageParam: 0,
    getNextPageParam: (last, pages) => {
      const loaded = pages.reduce((n, p) => n + p.items.length, 0)
      return loaded < last.total ? loaded : undefined
    },
  })

  const remove = useMutation({
    mutationFn: (id: string) => api.deleteHistory(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['history'] }),
    onError: (e) => toast.error(e.message),
  })
  const clear = useMutation({
    mutationFn: api.clearHistory,
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ['history'] })
      setConfirmClear(false)
      toast.success(`Deleted ${r.deleted} entr${r.deleted === 1 ? 'y' : 'ies'}`)
    },
    onError: (e) => toast.error(e.message),
  })

  const items = history.data?.pages.flatMap((p) => p.items) ?? []
  const total = history.data?.pages[0]?.total ?? 0

  return (
    <>
      <PageHeader
        title="History"
        description="Everything you have checked, asked or batch-processed in this browser. Open an entry to see its full result again."
        actions={
          <Button variant="danger" icon={<Trash2 className="size-4" />} onClick={() => setConfirmClear(true)} disabled={!total || kind !== 'all' || !!term}>
            Clear history
          </Button>
        }
      />
      <Card>
        <div className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-3">
          <Segmented<HistoryKind | 'all'>
            label="Type"
            value={kind}
            onChange={setKind}
            options={[
              { value: 'all', label: 'All' },
              { value: 'analyze', label: 'Diagnoses' },
              { value: 'nl2sql', label: 'Questions' },
              { value: 'batch', label: 'Batches' },
            ]}
          />
          <div className="relative ml-auto min-w-56">
            <Search className="pointer-events-none absolute top-2.5 left-2.5 size-4 text-ink-muted" />
            <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search queries, questions, classes" className="pl-8" aria-label="Search history" />
          </div>
        </div>

        {history.isLoading ? (
          <div className="space-y-2 p-4">
            {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-14" />)}
          </div>
        ) : history.error ? (
          <div className="p-4">
            <Callout tone="critical">{(history.error as Error).message}</Callout>
          </div>
        ) : items.length === 0 ? (
          <EmptyState icon={<HistoryIcon className="size-5" />} title={term || kind !== 'all' ? 'Nothing matches' : 'No history yet'}>
            {term || kind !== 'all' ? 'Try another search or type.' : 'Diagnoses, questions and batches you run appear here automatically.'}
          </EmptyState>
        ) : (
          <ul>
            {items.map((item) => {
              const k = KIND[item.kind]
              return (
                <li key={item.id} className="group flex items-center gap-3 border-b border-line px-4 py-3 last:border-0 hover:bg-surface-2/60">
                  <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-surface-2 text-ink-2" title={k.label}>
                    {k.icon}
                  </span>
                  <button type="button" onClick={() => navigate(`${k.path}?history=${item.id}`)} className="min-w-0 flex-1 text-left" title="Open">
                    <p className={item.kind === 'analyze' ? 'truncate font-mono text-[13px] text-ink' : 'truncate text-sm text-ink'}>{item.title}</p>
                    <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
                      <Outcome item={item} />
                      <ContextLabel ctx={item.context} names={names} />
                      <span className="text-xs text-ink-muted" title={new Date(item.created_at * 1000).toLocaleString()}>
                        {relativeTime(item.created_at)}
                      </span>
                    </div>
                  </button>
                  <IconButton label="Open" onClick={() => navigate(`${k.path}?history=${item.id}`)}>
                    <ArrowUpRight className="size-4" />
                  </IconButton>
                  <IconButton label="Delete entry" onClick={() => remove.mutate(item.id)} className="hover:text-critical-text">
                    <Trash2 className="size-4" />
                  </IconButton>
                </li>
              )
            })}
          </ul>
        )}
        {history.hasNextPage && (
          <div className="flex justify-center border-t border-line p-3">
            <Button onClick={() => history.fetchNextPage()} loading={history.isFetchingNextPage}>
              Load more ({total - items.length} left)
            </Button>
          </div>
        )}
      </Card>
      <Confirm open={confirmClear} onClose={() => setConfirmClear(false)} onConfirm={() => clear.mutate()} busy={clear.isPending} title="Clear all history?" confirmLabel="Clear history">
        All {total} entries will be deleted permanently. Saved schemas are kept.
      </Confirm>
    </>
  )
}
