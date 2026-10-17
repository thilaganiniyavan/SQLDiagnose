import { lazy, Suspense } from 'react'
import { Route, Routes } from 'react-router-dom'
import { Toaster } from 'sonner'
import ErrorBoundary from './components/ErrorBoundary'
import Layout from './components/Layout'
import { Spinner } from './components/ui'
import DiagnosePage from './pages/DiagnosePage'
import { useTheme } from './state/theme'

const AskPage = lazy(() => import('./pages/AskPage'))
const BatchPage = lazy(() => import('./pages/BatchPage'))
const SchemasPage = lazy(() => import('./pages/SchemasPage'))
const HistoryPage = lazy(() => import('./pages/HistoryPage'))
const ResultsPage = lazy(() => import('./pages/ResultsPage'))
const StatusPage = lazy(() => import('./pages/StatusPage'))
const NotFound = lazy(() => import('./pages/NotFound'))

function Loading() {
  return (
    <div className="flex justify-center py-24">
      <Spinner className="size-6" />
    </div>
  )
}

export default function App() {
  const { dark } = useTheme()
  return (
    <>
      <Routes>
        <Route element={<Layout />}>
          {[
            ['/', <DiagnosePage />],
            ['/ask', <AskPage />],
            ['/batch', <BatchPage />],
            ['/schemas', <SchemasPage />],
            ['/history', <HistoryPage />],
            ['/results', <ResultsPage />],
            ['/status', <StatusPage />],
            ['*', <NotFound />],
          ].map(([path, el]) => (
            <Route
              key={path as string}
              path={path as string}
              element={
                <ErrorBoundary>
                  <Suspense fallback={<Loading />}>{el}</Suspense>
                </ErrorBoundary>
              }
            />
          ))}
        </Route>
      </Routes>
      <Toaster theme={dark ? 'dark' : 'light'} position="bottom-right" richColors closeButton />
    </>
  )
}
