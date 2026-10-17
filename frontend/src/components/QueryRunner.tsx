import { useMutation } from '@tanstack/react-query'
import { Download, Play, TableIcon } from 'lucide-react'
import { useEffect } from 'react'
import { api } from '../lib/api'
import { download, toCsv } from '../lib/csv'
import { ms } from '../lib/format'
import type { ExecuteResult } from '../lib/types'
import { useDatabase } from '../state/database'
import { Button, Callout } from './ui'

/** "Run query" button + result table for the current database (read-only, server-limited). */
export default function QueryRunner({ sql, label = 'Run query', autoClearKey }: { sql: string; label?: string; autoClearKey?: unknown }) {
  const db = useDatabase()
  const run = useMutation({ mutationFn: (q: string) => api.execute({ query: q, ...db.executeTarget!, max_rows: 200 }) })
  const { reset } = run

  // a new query/result invalidates the previous output
  useEffect(() => reset(), [autoClearKey, sql, db.label, reset])

  const reason =
    db.selection.kind === 'none'
      ? 'Select a database to run queries.'
      : db.selection.kind === 'example'
        ? 'The data for the example databases is not installed on the server (make data).'
        : 'This schema has no data attached; import it from a SQLite file to run queries.'

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant="secondary" icon={<Play className="size-3.5" />} onClick={() => run.mutate(sql)} loading={run.isPending} disabled={!db.executable || !sql.trim()} title={db.executable ? `Run against ${db.label} (read-only)` : reason}>
          {label}
        </Button>
        {!db.executable && <span className="text-xs text-ink-muted">{reason}</span>}
      </div>
      {run.error && <Callout tone="critical" title="The query could not be run">{run.error.message}</Callout>}
      {run.data && <ResultTable result={run.data} />}
    </div>
  )
}

function renderCell(v: unknown) {
  if (v === null || v === undefined) return <span className="text-ink-muted italic">NULL</span>
  return String(v)
}

export function ResultTable({ result }: { result: ExecuteResult }) {
  const exportCsv = () =>
    download('query_result.csv', toCsv(result.rows.map((r) => Object.fromEntries(result.columns.map((c, i) => [c, r[i]]))), result.columns))
  return (
    <div className="overflow-hidden rounded-lg border border-line">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line bg-surface-2 px-3 py-1.5 text-xs text-ink-2">
        <span className="inline-flex items-center gap-1.5">
          <TableIcon className="size-3.5" />
          {result.row_count} row{result.row_count === 1 ? '' : 's'}
          {result.truncated && ' (first rows only)'} · {ms(result.elapsed_ms)}
        </span>
        {result.row_count > 0 && (
          <Button size="sm" variant="ghost" icon={<Download className="size-3.5" />} onClick={exportCsv}>
            CSV
          </Button>
        )}
      </div>
      {result.row_count === 0 ? (
        <p className="px-3 py-4 text-sm text-ink-muted">The query ran successfully and returned no rows.</p>
      ) : (
        <div className="scrollbar-thin max-h-80 overflow-auto">
          <table className="w-full text-left text-[13px]">
            <thead className="sticky top-0 bg-surface">
              <tr>
                {result.columns.map((c, i) => (
                  <th key={i} className="border-b border-line px-3 py-1.5 font-medium whitespace-nowrap text-ink">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {result.rows.map((r, i) => (
                <tr key={i} className="odd:bg-surface even:bg-surface-2/50">
                  {r.map((v, j) => (
                    <td key={j} className="max-w-xs truncate px-3 py-1 text-ink-2" title={v === null ? 'NULL' : String(v)}>
                      {renderCell(v)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
