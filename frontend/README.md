# SQLDiagnose web app

React 19 + TypeScript single-page app, built with Vite and styled with Tailwind CSS 4. In production the
FastAPI service serves the built files (`dist/`) and the API from the same origin.

```bash
npm ci
npm run dev          # http://localhost:5173, proxies /api to http://127.0.0.1:8000 (start it with `make api`)
npm run build        # type-checks and builds dist/ (served by the API at http://localhost:8000)
npm run lint         # ESLint (incl. React hooks rules)
npm test             # unit and component tests (Vitest + Testing Library)
npm run e2e          # Playwright end-to-end tests in Chromium against the real API
```

`SQLDIAGNOSE_API` changes the dev proxy target; `VITE_API_BASE` (build time) points the app at an API on
another origin (then add that origin to `api.cors_origins`). `E2E_BASE_URL` runs the end-to-end tests against an
already running server; otherwise Playwright starts the API itself.

## Structure

```
src/
  main.tsx, App.tsx       providers (theme, React Query, router, session, database) and lazy-loaded routes
  pages/                  Diagnose, Ask (NL→SQL), Batch, Schemas, History, Results, Status
  components/             app shell, SQL editor (CodeMirror), analysis view, schema browser, query runner,
                          dependency-free charts, UI primitives (ui.tsx)
  state/                  database context (selection + access policy, shared by all pages), theme,
                          session store (page state that survives navigation)
  lib/                    typed API client (api.ts, types.ts), error-class metadata, formatting, CSV, diff
e2e/                      Playwright tests
public/                   favicon, theme-init.js (applies the theme before first paint; external for the CSP)
```

Design tokens (light and dark) are CSS variables in `src/index.css`. Error classes use a fixed categorical
order validated for colour-vision deficiency; status colours (good / critical) are reserved for verdicts and
always come with an icon and a label.
