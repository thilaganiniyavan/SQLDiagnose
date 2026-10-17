import { expect, test, type Page } from '@playwright/test'

const CTRL = process.platform === 'darwin' ? 'Meta' : 'Control'

// The suite adapts to the server: CI runs it without the classifier checkpoint or the example data.
let hasModel = false
let hasData = false
test.beforeAll(async ({ request }) => {
  const health = await (await request.get('/api/v1/health')).json()
  hasModel = health.model_loaded
  hasData = health.executable_databases > 0
})

async function setQuery(page: Page, sql: string) {
  const editor = page.getByRole('textbox', { name: 'SQL query to diagnose' })
  await editor.click()
  await page.keyboard.press(`${CTRL}+A`)
  await page.keyboard.press('Delete')
  await page.keyboard.insertText(sql)
}

async function pickExample(page: Page, title: string) {
  await page.getByRole('button', { name: 'Examples' }).click()
  await page.getByRole('menuitem', { name: new RegExp(title) }).click()
}

test.describe('Diagnose & repair', () => {
  test('a query with several errors is diagnosed, repaired, re-checked and run', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('heading', { name: 'Diagnose & repair' })).toBeVisible()
    await pickExample(page, 'Several errors at once')
    await page.getByRole('button', { name: 'Analyze', exact: true }).click()

    await expect(page.getByRole('heading', { level: 2, name: 'Syntax error' })).toBeVisible()
    await expect(page.getByText('Verified fix')).toBeVisible()
    await expect(page.getByText('Repaired query', { exact: true })).toBeVisible()
    await expect(page.getByLabel('Changes made by the repair')).toContainText('FROM')

    await page.getByRole('button', { name: 'Use this query' }).click()
    await expect(page.getByRole('heading', { level: 2, name: 'No problems found' })).toBeVisible()
    if (hasData) {
      await page.getByRole('button', { name: 'Run query', exact: true }).click()
      await expect(page.getByText(/\d+ rows?/).first()).toBeVisible()
      await expect(page.locator('table thead th').first()).toBeVisible()
    } else {
      await expect(page.getByRole('button', { name: 'Run query', exact: true })).toBeDisabled()
    }
  })

  test('Ctrl+Enter analyzes, the classifier explains, and edits mark the result stale', async ({ page }) => {
    await page.goto('/')
    await setQuery(page, 'SELECT Nmae FROM singer')
    await page.keyboard.press(`${CTRL}+Enter`)
    await expect(page.getByRole('heading', { level: 2, name: 'Unknown column' })).toBeVisible()
    if (hasModel) {
      await expect(page.getByLabel('Class probabilities')).toBeVisible()
      await expect(page.getByText('Which words mattered')).toBeVisible()
    } else {
      await expect(page.getByRole('switch', { name: /Explain the prediction/ })).toBeDisabled()
    }
    await page.keyboard.type(' ')
    await expect(page.getByText('The query was edited after this analysis.')).toBeVisible()
  })

  test('restricted table example gives PERMISSION_DENIED and can be cleared', async ({ page }) => {
    await page.goto('/')
    await pickExample(page, 'Restricted table')
    await page.getByRole('button', { name: 'Analyze', exact: true }).click()
    await expect(page.getByRole('heading', { level: 2, name: 'Permission denied' })).toBeVisible()
    await expect(page.getByLabel(/Database: concert_singer/)).toContainText('1')
    await page.getByRole('button', { name: 'Clear', exact: true }).last().click()
    await page.getByRole('button', { name: 'Analyze', exact: true }).click()
    await expect(page.getByRole('heading', { level: 2, name: 'No problems found' })).toBeVisible()
  })

  test('shareable link runs a query on the given database', async ({ page }) => {
    await page.goto('/?q=' + encodeURIComponent('SELECT count(*) FROM cars_data') + '&db=car_1&run=1')
    await expect(page.getByRole('heading', { level: 2, name: 'No problems found' })).toBeVisible()
    await expect(page.getByLabel(/Database: car_1/)).toBeVisible()
    await expect(page).toHaveURL(/\/$/)
  })

  test('without a schema only grammar is checked', async ({ page }) => {
    await page.goto('/')
    await page.getByLabel(/Database:/).click()
    await page.getByRole('button', { name: /No schema/ }).click()
    await expect(page.getByText('No schema selected').first()).toBeVisible()
    await setQuery(page, 'SELECT a FORM t')
    await page.getByRole('button', { name: 'Analyze', exact: true }).click()
    await expect(page.getByRole('heading', { level: 2, name: 'Syntax error' })).toBeVisible()
  })
})

test('database picker filters and switches database', async ({ page }) => {
  await page.goto('/')
  await page.getByLabel(/Database:/).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('heading', { name: 'Choose a database' })).toBeVisible()
  await dialog.getByLabel('Filter databases').fill('flight')
  await dialog.getByRole('button', { name: /flight_2/ }).click()
  await expect(page.getByLabel(/Database: flight_2/)).toBeVisible()
  await expect(page.getByRole('button', { name: /airlines/ }).first()).toBeVisible()
})

test('import a schema from CREATE TABLE statements and use it', async ({ page }) => {
  await page.goto('/schemas')
  await page.getByLabel('CREATE TABLE statements').fill(
    'CREATE TABLE employees (id INT PRIMARY KEY, name VARCHAR(50), salary DECIMAL(10,2), dept_id INT REFERENCES depts(id));\nCREATE TABLE depts (id INT PRIMARY KEY, title VARCHAR(40));',
  )
  await page.getByRole('button', { name: 'Read schema' }).click()
  await expect(page.getByText(/Found 2 tables/)).toBeVisible()
  await page.getByLabel('Name', { exact: true }).fill('HR database')
  await page.getByRole('button', { name: 'Save and use' }).click()
  await expect(page.getByLabel(/Database: HR database/)).toBeVisible()
  await expect(page.getByText('HR database').first()).toBeVisible()

  await page.getByRole('link', { name: /Diagnose & repair/ }).click()
  await setQuery(page, 'SELECT name, salary FROM employee')
  await page.getByRole('button', { name: 'Analyze', exact: true }).click()
  await expect(page.getByRole('heading', { level: 2, name: 'Unknown table' })).toBeVisible()
  await expect(page.getByText('Verified fix')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Run repaired query' })).toBeDisabled()

  // restrict a column from the schema panel
  await page.getByRole('button', { name: 'Restrict column employees.salary' }).click()
  await setQuery(page, 'SELECT name, salary FROM employees')
  await page.getByRole('button', { name: 'Analyze', exact: true }).click()
  await expect(page.getByRole('heading', { level: 2, name: 'Permission denied' })).toBeVisible()

  // rename and delete
  await page.goto('/schemas')
  await page.getByRole('button', { name: 'Rename' }).first().click()
  await page.getByLabel('New name').fill('HR v2')
  await page.getByRole('button', { name: 'Save name' }).click()
  await expect(page.getByLabel(/Database: HR v2/)).toBeVisible()
  await page.getByRole('button', { name: 'Delete' }).first().click()
  await page.getByRole('dialog').getByRole('button', { name: 'Delete' }).click()
  await expect(page.getByText('No saved schemas yet')).toBeVisible()
  await expect(page.getByLabel(/Database: concert_singer/)).toBeVisible()
})

test('batch check with filtering and history', async ({ page }) => {
  await page.goto('/batch')
  await page.getByRole('button', { name: /Check 5 queries/ }).click()
  await expect(page.getByText('Checked 5 queries')).toBeVisible()
  await expect(page.getByText('With errors')).toBeVisible()
  const rows = page.locator('tbody tr')
  await expect(rows).toHaveCount(5)
  await page.getByRole('button', { name: /Errors \(4\)/ }).click()
  await expect(rows).toHaveCount(4)
  await rows.first().getByRole('button', { name: 'Expand' }).click()
  await expect(page.getByLabel('Changes made by the repair').first()).toBeVisible()

  await page.goto('/history')
  await expect(page.getByText('5 pasted queries')).toBeVisible()
  await page.getByText('5 pasted queries').click()
  await expect(page).toHaveURL(/\/batch$/)
  await expect(page.locator('tbody tr')).toHaveCount(5)
})

test('history records diagnoses, reopens them and can be cleared', async ({ page }) => {
  await page.goto('/')
  await setQuery(page, 'SELECT Name FROM singer WHERE Age = NULL')
  await page.getByRole('button', { name: 'Analyze', exact: true }).click()
  await expect(page.getByRole('heading', { level: 2, name: 'Semantic error' })).toBeVisible()

  await page.getByRole('link', { name: /History/ }).first().click()
  await expect(page.getByText('SELECT Name FROM singer WHERE Age = NULL')).toBeVisible()
  await page.getByLabel('Search history').fill('nothing-like-this')
  await expect(page.getByText('Nothing matches')).toBeVisible()
  await page.getByLabel('Search history').fill('NULL')
  await page.getByText('SELECT Name FROM singer WHERE Age = NULL').click()
  await expect(page.getByRole('heading', { level: 2, name: 'Semantic error' })).toBeVisible()

  await page.goto('/history')
  await page.getByRole('button', { name: 'Clear history' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Clear history' }).click()
  await expect(page.getByText('No history yet')).toBeVisible()
})

test('question to SQL shows progress and the verified result', async ({ page }) => {
  // The real generator needs ~1 minute per question on a CPU; the API is stubbed here.
  let polls = 0
  const result = {
    question: 'How many singers are older than 30?',
    sql: 'SELECT count(*) FROM singer WHERE Age > 30',
    status: 'valid_alternative',
    candidates: [
      { sql: 'SELECT count(*) FROM singers WHERE age > 30', confidence: 0.81, rank: 1, error_class: 'UNKNOWN_TABLE', issues: ["no such table: singers"] },
      { sql: 'SELECT count(*) FROM singer WHERE Age > 30', confidence: 0.12, rank: 2, error_class: 'CORRECT', issues: [] },
    ],
    repair: null,
    diagnosis: { query: 'SELECT count(*) FROM singer WHERE Age > 30', is_error: false, error_class: 'CORRECT', confidence: 1, decided_by: 'analyzer', analysis: null, model: null, notes: [] },
    generator: 'Qwen/Qwen2.5-Coder-0.5B-Instruct',
    prompt_truncated: false,
    generation_time_ms: 2100,
    latency_ms: 2300,
  }
  const job = (status: string, phase: string | null, res: unknown = null) => ({
    id: 'job1', kind: 'nl2sql', status, phase, queue_position: 0, result: res, error: null, created_at: 0, started_at: 0, finished_at: null, elapsed_s: 1,
  })
  await page.route('**/api/v1/nl2sql/jobs', (route) => route.fulfill({ status: 202, json: job('queued', null) }))
  await page.route('**/api/v1/nl2sql/jobs/job1', (route) => {
    polls += 1
    route.fulfill({ json: polls < 2 ? job('running', 'loading_model') : polls < 3 ? job('running', 'generating') : job('done', null, result) })
  })

  await page.goto('/ask')
  await page.getByRole('button', { name: 'How many singers are older than 30?' }).click()
  await page.getByRole('button', { name: 'Generate SQL' }).click()
  await expect(page.getByText('Working on it…')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Valid SQL (alternative)' })).toBeVisible({ timeout: 20_000 })
  await expect(page.getByText('SELECT count(*) FROM singers WHERE age > 30')).toBeVisible()
  if (hasData) {
    await page.getByRole('button', { name: 'Run query', exact: true }).click()
    await expect(page.getByText(/1 row/)).toBeVisible()
  }
  await page.getByRole('button', { name: 'Open in Diagnose' }).click()
  await expect(page.getByRole('heading', { level: 2, name: 'No problems found' })).toBeVisible()
})

test('research results, status page and theme', async ({ page }) => {
  await page.goto('/results')
  await expect(page.getByText('Error classification accuracy')).toBeVisible()
  await expect(page.getByLabel(/Confusion matrix/)).toBeVisible()
  await page.getByRole('radio', { name: 'Tables' }).click()
  await expect(page.getByRole('cell', { name: 'TF-IDF + LogReg' })).toBeVisible()
  await expect(page.locator('figure img').first()).toHaveJSProperty('complete', true)

  await page.goto('/status')
  await expect(page.getByText('Rule-based analyzer & repair engine')).toBeVisible()
  await expect(page.getByText('The eight classes')).toBeVisible()

  await page.getByRole('radio', { name: 'Dark theme' }).click()
  await expect(page.locator('html')).toHaveClass(/dark/)
  await page.reload()
  await expect(page.locator('html')).toHaveClass(/dark/)
  await page.getByRole('radio', { name: 'Light theme' }).click()
  await expect(page.locator('html')).not.toHaveClass(/dark/)
})

test('unknown routes show a not-found page', async ({ page }) => {
  await page.goto('/does-not-exist')
  await expect(page.getByText('Page not found')).toBeVisible()
})
