import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'

// Page state that survives navigating between pages (but not a reload): the last analysis,
// batch results, the running NL->SQL job, ...

type Store = Map<string, unknown>
const SessionContext = createContext<Store | null>(null)

export function SessionProvider({ children }: { children: ReactNode }) {
  const [store] = useState<Store>(() => new Map())
  return <SessionContext.Provider value={store}>{children}</SessionContext.Provider>
}

export function useSessionState<T>(key: string, initial: T | (() => T)): [T, (v: T | ((prev: T) => T)) => void] {
  const store = useContext(SessionContext)
  if (!store) throw new Error('useSessionState outside SessionProvider')
  const [value, setValue] = useState<T>(() => {
    if (store.has(key)) return store.get(key) as T
    const v = typeof initial === 'function' ? (initial as () => T)() : initial
    store.set(key, v)
    return v
  })
  const set = useCallback(
    (v: T | ((prev: T) => T)) => {
      setValue((prev) => {
        const next = typeof v === 'function' ? (v as (p: T) => T)(prev) : v
        store.set(key, next)
        return next
      })
    },
    [key, store],
  )
  return [value, set]
}
