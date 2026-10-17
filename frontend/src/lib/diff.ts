import { diffWordsWithSpace } from 'diff'

export interface DiffPart {
  value: string
  kind: 'same' | 'added' | 'removed'
}

/** Word-level diff between the original and the repaired query. */
export function wordDiff(before: string, after: string): DiffPart[] {
  return diffWordsWithSpace(before, after).map((p) => ({
    value: p.value,
    kind: p.added ? 'added' : p.removed ? 'removed' : 'same',
  }))
}
