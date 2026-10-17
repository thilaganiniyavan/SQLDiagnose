import { CLASS_META, classColorVar, classLabel } from '../lib/classes'
import type { ErrorClass } from '../lib/types'
import { cx } from '../lib/cx'

/** An error class: coloured dot for identity, label in ink (never colour alone). */
export default function ClassBadge({ value, size = 'md', className }: { value: ErrorClass | string | null | undefined; size?: 'sm' | 'md'; className?: string }) {
  if (!value) return <span className="text-ink-muted">—</span>
  const meta = CLASS_META[value as ErrorClass]
  return (
    <span
      title={meta ? `${value}: ${meta.hint}` : value}
      className={cx(
        'inline-flex items-center gap-1.5 rounded-full border border-line bg-surface font-medium whitespace-nowrap text-ink',
        size === 'sm' ? 'px-2 py-px text-xs' : 'px-2.5 py-0.5 text-[13px]',
        className,
      )}
    >
      <span className="size-2 shrink-0 rounded-full" style={{ background: classColorVar(value) }} aria-hidden />
      {classLabel(value)}
    </span>
  )
}
