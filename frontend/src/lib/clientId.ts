// Anonymous per-browser workspace id, sent as X-Client-Id so history and saved schemas
// stay separate between browsers sharing one deployment.

const KEY = 'sqld.clientId'
let cached: string | null = null

function generate(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return Array.from({ length: 32 }, () => Math.floor(Math.random() * 16).toString(16)).join('')
}

export function getClientId(): string {
  if (cached) return cached
  try {
    const stored = localStorage.getItem(KEY)
    if (stored && /^[A-Za-z0-9_-]{8,64}$/.test(stored)) {
      cached = stored
      return stored
    }
    cached = generate()
    localStorage.setItem(KEY, cached)
  } catch {
    cached = cached ?? generate()
  }
  return cached
}
