import { wordDiff } from '../lib/diff'

/** Word-level diff: removed words struck through, added words highlighted. */
export default function DiffView({ before, after }: { before: string; after: string }) {
  const parts = wordDiff(before, after)
  return (
    <div className="rounded-lg border border-line bg-surface-2 px-3.5 py-2.5" aria-label="Changes made by the repair">
      <code className="sql block text-ink">
        {parts.map((p, i) =>
          p.kind === 'same' ? (
            <span key={i}>{p.value}</span>
          ) : p.kind === 'removed' ? (
            <del key={i} className="mr-[3px] rounded-sm bg-critical-soft text-critical-text decoration-critical/70" title="removed">
              {p.value}
            </del>
          ) : (
            <ins key={i} className="rounded-sm bg-good-soft font-semibold text-good-text no-underline" title="added">
              {p.value}
            </ins>
          ),
        )}
      </code>
    </div>
  )
}
