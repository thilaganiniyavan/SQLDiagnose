import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import type { AnalyzeResponse } from '../../lib/types'
import { DatabaseProvider } from '../../state/database'
import { SessionProvider } from '../../state/session'
import { ThemeProvider } from '../../state/theme'
import AnalysisView from '../AnalysisView'
import ClassBadge from '../ClassBadge'
import DiffView from '../DiffView'
import SchemaBrowser from '../SchemaBrowser'

window.matchMedia ??= ((q: string) => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {} })) as unknown as typeof window.matchMedia

function wrap(ui: ReactNode) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ db_id: 'concert_singer', database_schema: {}, ddl: '', executable: true }))))
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <ThemeProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <SessionProvider>
            <DatabaseProvider>{ui}</DatabaseProvider>
          </SessionProvider>
        </MemoryRouter>
      </QueryClientProvider>
    </ThemeProvider>,
  )
}

const RESULT: AnalyzeResponse = {
  diagnosis: {
    query: 'SELECT nme FROM singer',
    is_error: true,
    error_class: 'UNKNOWN_COLUMN',
    description: 'The query references a column that does not exist.',
    confidence: 1,
    decided_by: 'analyzer+model',
    analysis: { error_class: 'UNKNOWN_COLUMN', is_error: true, issues: [{ error_class: 'UNKNOWN_COLUMN', message: "Column 'nme' does not exist.", token: 'nme', source: 'engine' }], engine_error: null, schema_checked: true },
    model: { error_class: 'UNKNOWN_COLUMN', confidence: 0.9, probabilities: { CORRECT: 0.05, UNKNOWN_COLUMN: 0.9, SYNTAX_ERROR: 0.05 } },
    notes: [],
    explanation: { query_tokens: [{ token: 'nme', score: 0.8 }, { token: 'FROM', score: -0.1 }] },
    latency_ms: 12,
  },
  repair: {
    original_query: 'SELECT nme FROM singer',
    repaired_query: 'SELECT name FROM singer',
    success: true,
    remaining_error: null,
    steps: [{ error_class: 'UNKNOWN_COLUMN', description: "Replaced 'nme' with 'name'.", before: 'SELECT nme FROM singer', after: 'SELECT name FROM singer' }],
    explanation: 'Fixed.',
  },
  latency_ms: 30,
  history_id: null,
}

describe('ClassBadge', () => {
  it('shows a readable label with the class name as tooltip', () => {
    render(<ClassBadge value="AMBIGUOUS_REFERENCE" />)
    expect(screen.getByText('Ambiguous reference')).toHaveAttribute('title', expect.stringContaining('AMBIGUOUS_REFERENCE'))
  })
})

describe('DiffView', () => {
  it('renders removed and added words', () => {
    const { container } = render(<DiffView before="SELECT nme FROM t" after="SELECT name FROM t" />)
    expect(container.querySelector('del')?.textContent?.trim()).toBe('nme')
    expect(container.querySelector('ins')?.textContent?.trim()).toBe('name')
  })
})

describe('AnalysisView', () => {
  it('shows verdict, issue, verified fix, probabilities and attributions', async () => {
    const onUse = vi.fn()
    wrap(<AnalysisView result={RESULT} onUseQuery={onUse} />)
    expect(screen.getByRole('heading', { level: 2, name: 'Unknown column' })).toBeInTheDocument()
    expect(screen.getByText("Column 'nme' does not exist.")).toBeInTheDocument()
    expect(screen.getByText('Verified fix')).toBeInTheDocument()
    expect(screen.getByLabelText('Class probabilities')).toBeInTheDocument()
    expect(screen.getByTitle('nme: +0.8000')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Use this query' }))
    expect(onUse).toHaveBeenCalledWith('SELECT name FROM singer')
  })

  it('shows a success state for correct queries', () => {
    wrap(<AnalysisView result={{ ...RESULT, repair: null, diagnosis: { ...RESULT.diagnosis, is_error: false, error_class: 'CORRECT', analysis: null, model: null, explanation: null } }} />)
    expect(screen.getByRole('heading', { level: 2, name: 'No problems found' })).toBeInTheDocument()
    expect(screen.queryByText('Verified fix')).not.toBeInTheDocument()
  })
})

describe('SchemaBrowser', () => {
  const schema = {
    singer: { columns: { singer_id: 'INTEGER', name: 'TEXT' }, primary_keys: ['singer_id'] },
    concert: { columns: { id: 'INTEGER' } },
  }

  it('inserts names and toggles restrictions', async () => {
    const onInsert = vi.fn()
    const onPolicy = vi.fn()
    render(<SchemaBrowser schema={schema} onInsert={onInsert} policy={{ restricted_tables: [], restricted_columns: [] }} onPolicyChange={onPolicy} />)
    await userEvent.click(screen.getByRole('button', { name: 'name' }))
    expect(onInsert).toHaveBeenCalledWith('name')
    await userEvent.click(screen.getByRole('button', { name: 'Restrict table singer' }))
    expect(onPolicy).toHaveBeenCalledWith({ restricted_tables: ['singer'], restricted_columns: [] })
    await userEvent.click(screen.getByRole('button', { name: 'Restrict column singer.name' }))
    expect(onPolicy).toHaveBeenLastCalledWith({ restricted_tables: [], restricted_columns: ['singer.name'] })
  })
})
