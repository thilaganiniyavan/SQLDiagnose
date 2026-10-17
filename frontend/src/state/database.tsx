import { useQuery, useQueryClient } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { toast } from 'sonner'
import { api } from '../lib/api'
import { EXAMPLE_DB } from '../lib/examples'
import { load, save } from '../lib/storage'
import type { AccessPolicy, DatabaseSchema, SchemaContextBody } from '../lib/types'

// The database the user is working against, shared by every page: a bundled example database,
// a schema saved in the workspace, or none (grammar and schema-independent checks only).

export type Selection = { kind: 'example'; dbId: string } | { kind: 'saved'; id: string; name: string } | { kind: 'none' }

interface DatabaseValue {
  selection: Selection
  /** Switches database; `policy` (if given) becomes that database's access policy. */
  select: (s: Selection, policy?: AccessPolicy) => void
  schema: DatabaseSchema | null
  ddl: string | null
  loading: boolean
  error: string | null
  /** Display name of the selection. */
  label: string
  policy: AccessPolicy
  setPolicy: (p: AccessPolicy) => void
  /** Schema fields for query requests. */
  body: SchemaContextBody
  /** Whether queries can be run against real data, and against what. */
  executable: boolean
  executeTarget: { db_id?: string; schema_id?: string } | null
}

const DatabaseContext = createContext<DatabaseValue | null>(null)
const EMPTY: AccessPolicy = { restricted_tables: [], restricted_columns: [] }
const keyOf = (s: Selection) => (s.kind === 'example' ? `example:${s.dbId}` : s.kind === 'saved' ? `saved:${s.id}` : 'none')

export function DatabaseProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient()
  const [selection, setSelection] = useState<Selection>(() => load<Selection>('sqld.selection', { kind: 'example', dbId: EXAMPLE_DB }))
  const [policies, setPolicies] = useState<Record<string, AccessPolicy>>(() => load('sqld.policies', {}))

  const example = useQuery({
    queryKey: ['example-schema', selection.kind === 'example' ? selection.dbId : null],
    queryFn: () => api.exampleSchema((selection as { dbId: string }).dbId),
    enabled: selection.kind === 'example',
    staleTime: Infinity,
    retry: 1,
  })
  const saved = useQuery({
    queryKey: ['saved-schema', selection.kind === 'saved' ? selection.id : null],
    queryFn: () => api.savedSchema((selection as { id: string }).id),
    enabled: selection.kind === 'saved',
    retry: 1,
  })
  const active = selection.kind === 'example' ? example : selection.kind === 'saved' ? saved : null
  const missing = (active?.error as { status?: number } | null)?.status === 404

  // A saved schema deleted elsewhere, or an example database no longer bundled: fall back.
  // (Synchronises with server state, so setting state here is intended.)
  useEffect(() => {
    if (missing) {
      toast.warning('The selected database is no longer available; switched to the example database.')
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSelection({ kind: 'example', dbId: EXAMPLE_DB })
    }
  }, [missing])

  useEffect(() => save('sqld.selection', selection), [selection])
  useEffect(() => save('sqld.policies', policies), [policies])

  const key = keyOf(selection)
  const savedPolicy = selection.kind === 'saved' ? saved.data?.access_policy ?? null : null
  const policy = policies[key] ?? savedPolicy ?? EMPTY

  const setPolicy = useCallback(
    (p: AccessPolicy) => {
      setPolicies((prev) => ({ ...prev, [key]: p }))
      if (selection.kind === 'saved') {
        const empty = !p.restricted_tables.length && !p.restricted_columns.length
        api
          .updateSavedSchema(selection.id, empty ? { clear_access_policy: true } : { access_policy: p })
          .then((s) => qc.setQueryData(['saved-schema', s.id], (old: object | undefined) => ({ ...old, ...s })))
          .catch((e) => toast.error(`Could not save the access policy: ${e.message}`))
      }
    },
    [key, selection, qc],
  )

  const select = useCallback((s: Selection, p?: AccessPolicy) => {
    setSelection(s)
    if (p) setPolicies((prev) => ({ ...prev, [keyOf(s)]: p }))
  }, [])

  const value = useMemo<DatabaseValue>(() => {
    const schema = selection.kind === 'example' ? example.data?.database_schema ?? null : selection.kind === 'saved' ? saved.data?.database_schema ?? null : null
    const ddl = selection.kind === 'example' ? example.data?.ddl ?? null : selection.kind === 'saved' ? saved.data?.ddl ?? null : null
    const hasPolicy = policy.restricted_tables.length > 0 || policy.restricted_columns.length > 0
    let body: SchemaContextBody = {}
    if (selection.kind === 'example') body = { db_id: selection.dbId }
    if (selection.kind === 'saved') body = { schema_id: selection.id, access_policy: policy }
    if (hasPolicy && selection.kind !== 'none') body.access_policy = policy
    const executable =
      selection.kind === 'example' ? !!example.data?.executable : selection.kind === 'saved' ? !!saved.data?.executable : false
    return {
      selection,
      select,
      schema,
      ddl,
      loading: !!active?.isLoading,
      error: active?.error ? (active.error as Error).message : null,
      label: selection.kind === 'example' ? selection.dbId : selection.kind === 'saved' ? saved.data?.name ?? selection.name : 'No schema',
      policy,
      setPolicy,
      body,
      executable,
      executeTarget: !executable ? null : selection.kind === 'example' ? { db_id: selection.dbId } : selection.kind === 'saved' ? { schema_id: selection.id } : null,
    }
  }, [selection, select, example.data, saved.data, active, policy, setPolicy])

  return <DatabaseContext.Provider value={value}>{children}</DatabaseContext.Provider>
}

export function useDatabase(): DatabaseValue {
  const ctx = useContext(DatabaseContext)
  if (!ctx) throw new Error('useDatabase outside DatabaseProvider')
  return ctx
}

/** Columns and tables of the current schema, for editor autocompletion. */
export function completionSchema(schema: DatabaseSchema | null): Record<string, string[]> {
  if (!schema) return {}
  return Object.fromEntries(Object.entries(schema).map(([t, info]) => [t, Object.keys(info.columns ?? {})]))
}

/** Restores the database (and access policy) a history entry was run against. */
export function useApplyContext() {
  const { select } = useDatabase()
  return useCallback(
    (ctx: SchemaContextBody): boolean => {
      const policy = ctx.access_policy ?? EMPTY
      if (ctx.db_id) select({ kind: 'example', dbId: ctx.db_id }, policy)
      else if (ctx.schema_id) select({ kind: 'saved', id: ctx.schema_id, name: 'Saved schema' }, ctx.access_policy)
      else if (ctx.database_schema) return false
      else select({ kind: 'none' })
      return true
    },
    [select],
  )
}
