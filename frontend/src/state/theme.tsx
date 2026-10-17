import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

export type ThemePref = 'system' | 'light' | 'dark'

interface ThemeValue {
  pref: ThemePref
  dark: boolean
  setPref: (p: ThemePref) => void
}

const ThemeContext = createContext<ThemeValue | null>(null)
const media = () => window.matchMedia('(prefers-color-scheme: dark)')

function readPref(): ThemePref {
  try {
    const v = localStorage.getItem('sqld.theme')
    return v === 'light' || v === 'dark' ? v : 'system'
  } catch {
    return 'system'
  }
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [pref, setPrefState] = useState<ThemePref>(readPref)
  const [systemDark, setSystemDark] = useState(() => media().matches)

  useEffect(() => {
    const m = media()
    const onChange = () => setSystemDark(m.matches)
    m.addEventListener('change', onChange)
    return () => m.removeEventListener('change', onChange)
  }, [])

  const dark = pref === 'dark' || (pref === 'system' && systemDark)
  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
    document.documentElement.style.colorScheme = dark ? 'dark' : 'light'
  }, [dark])

  const setPref = useCallback((p: ThemePref) => {
    setPrefState(p)
    try {
      // stored as a plain string: public/theme-init.js reads it before React loads
      if (p === 'system') localStorage.removeItem('sqld.theme')
      else localStorage.setItem('sqld.theme', p)
    } catch {
      /* not remembered */
    }
  }, [])

  const value = useMemo(() => ({ pref, dark, setPref }), [pref, dark, setPref])
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme(): ThemeValue {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme outside ThemeProvider')
  return ctx
}

