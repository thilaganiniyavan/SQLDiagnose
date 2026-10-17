import {
  Activity,
  BarChart3,
  ChevronDown,
  Database,
  FileStack,
  History,
  Lock,
  Menu,
  MessageSquareText,
  Monitor,
  Moon,
  Stethoscope,
  Sun,
  X,
} from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useHealth } from '../lib/queries'
import { useDatabase } from '../state/database'
import { useTheme, type ThemePref } from '../state/theme'
import DatabasePicker from './DatabasePicker'
import { IconButton } from './ui'
import { cx } from '../lib/cx'

const NAV: { to: string; label: string; icon: ReactNode; hint: string }[] = [
  { to: '/', label: 'Diagnose & repair', icon: <Stethoscope className="size-4" />, hint: 'Check one query' },
  { to: '/ask', label: 'Question → SQL', icon: <MessageSquareText className="size-4" />, hint: 'Ask in plain English' },
  { to: '/batch', label: 'Batch check', icon: <FileStack className="size-4" />, hint: 'Many queries / CSV' },
  { to: '/schemas', label: 'Schemas', icon: <Database className="size-4" />, hint: 'Import & manage' },
  { to: '/history', label: 'History', icon: <History className="size-4" />, hint: 'Your past runs' },
  { to: '/results', label: 'Research results', icon: <BarChart3 className="size-4" />, hint: 'Evaluation' },
  { to: '/status', label: 'Service status', icon: <Activity className="size-4" />, hint: 'Models & activity' },
]

function Brand() {
  return (
    <div className="flex items-center gap-2.5 px-2">
      <img src="/favicon.svg" alt="" className="size-7" />
      <div className="leading-tight">
        <p className="text-[15px] font-semibold tracking-tight text-ink">SQLDiagnose</p>
        <p className="text-[11px] text-ink-muted">diagnose · repair · generate</p>
      </div>
    </div>
  )
}

function ThemeSwitch() {
  const { pref, setPref } = useTheme()
  const opts: { v: ThemePref; icon: ReactNode; label: string }[] = [
    { v: 'light', icon: <Sun className="size-3.5" />, label: 'Light theme' },
    { v: 'system', icon: <Monitor className="size-3.5" />, label: 'System theme' },
    { v: 'dark', icon: <Moon className="size-3.5" />, label: 'Dark theme' },
  ]
  return (
    <div role="radiogroup" aria-label="Theme" className="inline-flex rounded-lg border border-line bg-surface-2 p-0.5">
      {opts.map((o) => (
        <button
          key={o.v}
          type="button"
          role="radio"
          aria-checked={pref === o.v}
          aria-label={o.label}
          title={o.label}
          onClick={() => setPref(o.v)}
          className={cx('inline-flex size-7 items-center justify-center rounded-md', pref === o.v ? 'bg-surface text-ink shadow-card' : 'text-ink-muted hover:text-ink')}
        >
          {o.icon}
        </button>
      ))}
    </div>
  )
}

function StatusLine() {
  const health = useHealth()
  const h = health.data
  const state = health.isError ? 'offline' : !h ? 'checking' : 'online'
  return (
    <NavLink to="/status" className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-xs text-ink-2 hover:bg-surface-2" title="Service status">
      <span className={cx('size-2 rounded-full', state === 'online' ? 'bg-good' : state === 'offline' ? 'bg-critical' : 'bg-warning')} aria-hidden />
      <span className="min-w-0 flex-1 truncate">
        {state === 'offline' ? 'API offline' : state === 'checking' ? 'Connecting…' : h?.model_loaded ? 'Analyzer + classifier ready' : 'Analyzer ready (no classifier)'}
      </span>
    </NavLink>
  )
}

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <div className="flex h-full flex-col gap-4 px-3 py-4">
      <Brand />
      <nav aria-label="Main" className="flex-1 space-y-0.5">
        {NAV.map((n) => (
          <NavLink
            key={n.to}
            to={n.to}
            end={n.to === '/'}
            onClick={onNavigate}
            className={({ isActive }) =>
              cx(
                'flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition-colors',
                isActive ? 'bg-surface font-medium text-ink shadow-card ring-1 ring-line' : 'text-ink-2 hover:bg-surface-2 hover:text-ink',
              )
            }
          >
            {n.icon}
            <span className="flex-1">{n.label}</span>
          </NavLink>
        ))}
      </nav>
      <div className="space-y-2 border-t border-line pt-3">
        <StatusLine />
        <div className="flex items-center justify-between px-2">
          <span className="text-xs text-ink-muted">Theme</span>
          <ThemeSwitch />
        </div>
      </div>
    </div>
  )
}

function DatabaseChip({ onClick }: { onClick: () => void }) {
  const db = useDatabase()
  const tables = db.schema ? Object.keys(db.schema).length : 0
  const locks = db.policy.restricted_tables.length + db.policy.restricted_columns.length
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={`Database: ${db.label}. Change database`}
      className="flex max-w-full min-w-0 items-center gap-2.5 rounded-lg border border-line-strong bg-surface px-3 py-1.5 text-left shadow-card transition-colors hover:border-accent"
    >
      <Database className="size-4 shrink-0 text-accent-text" />
      <span className="min-w-0">
        <span className="block text-[11px] leading-tight text-ink-muted">Database</span>
        <span className={cx('block truncate text-sm leading-tight font-medium', db.selection.kind === 'example' && 'font-mono text-[13px]')}>{db.label}</span>
      </span>
      {db.selection.kind !== 'none' && (
        <span className="hidden shrink-0 text-xs text-ink-muted sm:inline">{db.loading ? '…' : `${tables} tables`}</span>
      )}
      {locks > 0 && (
        <span className="inline-flex shrink-0 items-center gap-0.5 text-xs text-critical-text" title={`${locks} restricted table(s)/column(s)`}>
          <Lock className="size-3" />
          {locks}
        </span>
      )}
      <ChevronDown className="size-4 shrink-0 text-ink-muted" />
    </button>
  )
}

export default function Layout() {
  const [pickerOpen, setPickerOpen] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const location = useLocation()
  const current = NAV.find((n) => (n.to === '/' ? location.pathname === '/' : location.pathname.startsWith(n.to)))

  useEffect(() => {
    document.title = current ? `${current.label} · SQLDiagnose` : 'SQLDiagnose'
  }, [current])

  useEffect(() => {
    const open = () => setPickerOpen(true)
    window.addEventListener('sqld:pick-database', open)
    return () => window.removeEventListener('sqld:pick-database', open)
  }, [])

  return (
    <div className="flex h-full">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-surface focus:px-3 focus:py-2">
        Skip to content
      </a>
      <aside className="hidden w-60 shrink-0 border-r border-line bg-page lg:block">
        <Sidebar />
      </aside>

      {menuOpen && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
          <div className="absolute inset-0 bg-black/40" onClick={() => setMenuOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-64 bg-page shadow-pop">
            <div className="absolute top-3 right-2">
              <IconButton label="Close menu" onClick={() => setMenuOpen(false)}>
                <X className="size-4" />
              </IconButton>
            </div>
            <Sidebar onNavigate={() => setMenuOpen(false)} />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-line bg-page/85 px-4 py-2.5 backdrop-blur sm:px-6">
          <IconButton label="Open menu" className="lg:hidden" onClick={() => setMenuOpen(true)}>
            <Menu className="size-5" />
          </IconButton>
          <p className="hidden min-w-0 truncate text-sm text-ink-muted md:block">
            {current ? (
              <>
                <span className="font-medium text-ink">{current.label}</span> · {current.hint}
              </>
            ) : null}
          </p>
          <div className="ml-auto min-w-0">
            <DatabaseChip onClick={() => setPickerOpen(true)} />
          </div>
        </header>
        <main id="main" className="scrollbar-thin min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-[1400px] px-4 py-6 sm:px-6 lg:py-8">
            <Outlet />
          </div>
        </main>
      </div>
      <DatabasePicker open={pickerOpen} onClose={() => setPickerOpen(false)} />
    </div>
  )
}

/** Opens the database picker from anywhere (e.g. an empty-state button). */
// eslint-disable-next-line react-refresh/only-export-components
export const openDatabasePicker = () => window.dispatchEvent(new Event('sqld:pick-database'))
