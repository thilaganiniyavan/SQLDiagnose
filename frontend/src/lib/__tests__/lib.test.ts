import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, request } from '../api'
import { CLASS_ORDER, classColorVar, classLabel } from '../classes'
import { splitQueries, toCsv } from '../csv'
import { wordDiff } from '../diff'
import { duration, ms, pct, relativeTime } from '../format'

describe('splitQueries', () => {
  it('splits one query per line and drops blanks', () => {
    expect(splitQueries('SELECT 1\n\n  SELECT 2  \r\n', 'lines')).toEqual(['SELECT 1', 'SELECT 2'])
  })
  it('splits on semicolons outside quotes and joins lines', () => {
    expect(splitQueries("SELECT a\nFROM t WHERE b = 'x;y';\nSELECT \"c;d\" FROM u;", 'semicolons')).toEqual([
      "SELECT a FROM t WHERE b = 'x;y'",
      'SELECT "c;d" FROM u',
    ])
  })
})

describe('toCsv', () => {
  it('quotes cells with commas, quotes and newlines, and joins arrays', () => {
    const csv = toCsv([{ q: 'SELECT a, b', n: 1, issues: ['x', 'y'], s: 'say "hi"' }, { q: 'line\nbreak', n: null }], ['q', 'n', 'issues', 's'])
    expect(csv).toBe('q,n,issues,s\n"SELECT a, b",1,x; y,"say ""hi"""\n"line\nbreak",,,\n')
  })
})

describe('wordDiff', () => {
  it('marks removed and added words', () => {
    const parts = wordDiff('SELECT nme FROM singer', 'SELECT name FROM singer')
    expect(parts.filter((p) => p.kind === 'removed').map((p) => p.value.trim())).toEqual(['nme'])
    expect(parts.filter((p) => p.kind === 'added').map((p) => p.value.trim())).toEqual(['name'])
    expect(parts.map((p) => (p.kind === 'removed' ? '' : p.value)).join('')).toBe('SELECT name FROM singer')
  })
})

describe('format', () => {
  it('formats percentages, durations and latencies', () => {
    expect(pct(0.8742)).toBe('87.4%')
    expect(pct(null)).toBe('—')
    expect(ms(0.4)).toBe('<1 ms')
    expect(ms(343.4)).toBe('343 ms')
    expect(ms(47572)).toBe('48 s')
    expect(duration(75)).toBe('1 min 15 s')
    expect(relativeTime(1000, 1000 * 1000 + 30_000)).toBe('just now')
    expect(relativeTime(1000, (1000 + 7200) * 1000)).toBe('2 h ago')
  })
})

describe('classes', () => {
  it('covers the eight classes with labels and colours', () => {
    expect(CLASS_ORDER).toHaveLength(8)
    expect(classLabel('UNKNOWN_COLUMN')).toBe('Unknown column')
    expect(classLabel('SOMETHING_NEW')).toBe('SOMETHING_NEW')
    expect(classColorVar('CORRECT')).toBe('var(--good)')
    expect(new Set(CLASS_ORDER.map(classColorVar)).size).toBe(8)
  })
})

describe('request', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('sends the client id and JSON body', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: 1 }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    await expect(request('/x', { body: { a: 1 } })).resolves.toEqual({ ok: 1 })
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toMatch(/\/api\/v1\/x$/)
    expect(init.method).toBe('POST')
    expect(init.headers['X-Client-Id']).toMatch(/^[A-Za-z0-9_-]{8,64}$/)
    expect(init.body).toBe('{"a":1}')
  })

  it('turns FastAPI errors into readable ApiErrors', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "Unknown example database 'x'." }), { status: 404 })))
    await expect(request('/x')).rejects.toMatchObject({ status: 404, message: "Unknown example database 'x'." })
    const validation = { detail: [{ loc: ['body', 'query'], msg: 'String should have at least 1 character' }] }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(validation), { status: 422 })))
    await expect(request('/x', { body: {} })).rejects.toMatchObject({ message: 'query: String should have at least 1 character' })
  })

  it('reports an unreachable server', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    const err = (await request('/x').catch((e: unknown) => e)) as ApiError
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(0)
    expect(err.message).toMatch(/Cannot reach/)
  })
})
