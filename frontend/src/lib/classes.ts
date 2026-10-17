import type { ErrorClass } from './types'

export const CLASS_ORDER: ErrorClass[] = [
  'CORRECT',
  'SYNTAX_ERROR',
  'UNKNOWN_TABLE',
  'UNKNOWN_COLUMN',
  'DATATYPE_MISMATCH',
  'AMBIGUOUS_REFERENCE',
  'PERMISSION_DENIED',
  'SEMANTIC_ERROR',
]

interface ClassMeta {
  label: string
  short: string
  /** Index into the categorical palette (--cat-1..7); CORRECT uses the status "good" colour. */
  slot: number
  hint: string
}

export const CLASS_META: Record<ErrorClass, ClassMeta> = {
  CORRECT: { label: 'Correct', short: 'OK', slot: 0, hint: 'No problem found.' },
  SYNTAX_ERROR: { label: 'Syntax error', short: 'Syntax', slot: 1, hint: 'Misspelled or missing keyword, comma, parenthesis or quote.' },
  UNKNOWN_TABLE: { label: 'Unknown table', short: 'Table', slot: 2, hint: 'A table that is not in the schema.' },
  UNKNOWN_COLUMN: { label: 'Unknown column', short: 'Column', slot: 3, hint: 'A column that is not in the referenced table.' },
  DATATYPE_MISMATCH: { label: 'Type mismatch', short: 'Type', slot: 4, hint: 'Incompatible types compared or aggregated.' },
  AMBIGUOUS_REFERENCE: { label: 'Ambiguous reference', short: 'Ambiguous', slot: 5, hint: 'A name that matches several tables, or a reused alias.' },
  PERMISSION_DENIED: { label: 'Permission denied', short: 'Permission', slot: 6, hint: 'Touches a table or column the access policy restricts.' },
  SEMANTIC_ERROR: { label: 'Semantic error', short: 'Semantic', slot: 7, hint: 'Grammatical but logically invalid.' },
}

export function classLabel(c: string | null | undefined): string {
  if (!c) return '—'
  return CLASS_META[c as ErrorClass]?.label ?? c
}

export function classColorVar(c: string): string {
  const meta = CLASS_META[c as ErrorClass]
  if (!meta) return 'var(--ink-muted)'
  return meta.slot === 0 ? 'var(--good)' : `var(--cat-${meta.slot})`
}

export const DECIDED_BY: Record<string, string> = {
  analyzer: 'Rule-based analyzer',
  model: 'Neural classifier',
  'analyzer+model': 'Analyzer, confirmed by the classifier',
}

export const ISSUE_SOURCE: Record<string, string> = {
  engine: 'SQLite compiler',
  static: 'Static rule',
  policy: 'Access policy',
}
