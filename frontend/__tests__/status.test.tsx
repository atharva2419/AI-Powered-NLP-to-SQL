/**
 * Tests for the signals the backend added alongside the answer itself:
 * whether it came from cache, whether the model had to correct itself,
 * whether the result set was capped, and whether the demo throttled us.
 */
import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import Home from '@/app/page'
import * as api from '@/lib/api'

jest.mock('react-syntax-highlighter', () => ({
  Light: Object.assign(
    function MockHighlighter({ children }: { children: React.ReactNode }) {
      return <pre data-testid="sql-block">{children}</pre>
    },
    { registerLanguage: jest.fn() }
  ),
}))
jest.mock('react-syntax-highlighter/dist/esm/languages/hljs/sql', () => ({}))
jest.mock('react-syntax-highlighter/dist/esm/styles/hljs', () => ({ atomOneDark: {} }))
jest.mock('@/components/ResultChart', () => ({
  __esModule: true,
  default: () => <div data-testid="result-chart" />,
}))

jest.mock('@/lib/api')
const mockFetchExamples = api.fetchExamples as jest.MockedFunction<typeof api.fetchExamples>
const mockFetchSchema = api.fetchSchema as jest.MockedFunction<typeof api.fetchSchema>
const mockRunQuery = api.runQuery as jest.MockedFunction<typeof api.runQuery>
const mockFetchHistory = api.fetchHistory as jest.MockedFunction<typeof api.fetchHistory>

const BASE: api.QueryResponse = {
  sql: 'SELECT COUNT(*) FROM taxi',
  result: { columns: ['trips'], rows: [[5]], row_count: 1 },
  explanation: 'There were 5 trips.',
  latency_ms: 1500,
}

beforeEach(() => {
  mockFetchExamples.mockResolvedValue([])
  mockFetchSchema.mockResolvedValue({ columns: [], rowCount: 41_000_000 })
  mockFetchHistory.mockResolvedValue([])
  mockRunQuery.mockReset()
})

async function ask(response: api.QueryResponse) {
  mockRunQuery.mockResolvedValue(response)
  render(<Home />)
  fireEvent.change(screen.getByPlaceholderText(/average fare/i), {
    target: { value: 'How many trips?' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Ask' }))
  await waitFor(() => expect(screen.getByTestId('sql-block')).toBeInTheDocument())
}

describe('cache badge', () => {
  it('appears when the answer came from cache', async () => {
    await ask({ ...BASE, cached: true })
    expect(screen.getByText('cached')).toBeInTheDocument()
  })

  it('is absent for a freshly generated answer', async () => {
    await ask({ ...BASE, cached: false })
    expect(screen.queryByText('cached')).not.toBeInTheDocument()
  })

  it('is absent when the backend omits the field', async () => {
    await ask(BASE)
    expect(screen.queryByText('cached')).not.toBeInTheDocument()
  })
})

describe('self-correction badge', () => {
  it('appears when the model needed more than one attempt', async () => {
    await ask({ ...BASE, attempts: 2 })
    expect(screen.getByText(/self-corrected \(2 attempts\)/i)).toBeInTheDocument()
  })

  it('is absent on a first-attempt success', async () => {
    await ask({ ...BASE, attempts: 1 })
    expect(screen.queryByText(/self-corrected/i)).not.toBeInTheDocument()
  })

  it('is absent when the backend omits the field', async () => {
    await ask(BASE)
    expect(screen.queryByText(/self-corrected/i)).not.toBeInTheDocument()
  })
})

describe('truncation notice', () => {
  it('says the server capped the result', async () => {
    const rows = Array.from({ length: 100 }, (_, i) => [i])
    await ask({
      ...BASE,
      result: { columns: ['n'], rows, row_count: 100, truncated: true },
    })
    expect(screen.getByText(/result capped by the server/i)).toBeInTheDocument()
  })

  it('is absent when the whole result fits', async () => {
    await ask(BASE)
    expect(screen.queryByText(/result capped/i)).not.toBeInTheDocument()
  })
})

describe('dataset size', () => {
  async function renderWithRows(rowCount: number) {
    mockFetchSchema.mockResolvedValue({ columns: [], rowCount })
    render(<Home />)
    await waitFor(() => expect(mockFetchSchema).toHaveBeenCalled())
  }

  it('states the real dataset size rather than a hardcoded number', async () => {
    await renderWithRows(1_000_000)
    await waitFor(() => expect(screen.getByText(/1\.0M/)).toBeInTheDocument())
  })

  it('flags a sampled dataset', async () => {
    // The hosted demo runs ~1M rows. Claiming 41M there would be a lie the
    // reader has no way to check.
    await renderWithRows(1_000_000)
    await waitFor(() => expect(screen.getByText('sample')).toBeInTheDocument())
  })

  it('does not flag the full dataset', async () => {
    await renderWithRows(41_000_000)
    await waitFor(() => expect(screen.getByText(/41\.0M/)).toBeInTheDocument())
    expect(screen.queryByText('sample')).not.toBeInTheDocument()
  })

  it('falls back gracefully when the backend is unreachable', async () => {
    mockFetchSchema.mockRejectedValue(new Error('offline'))
    render(<Home />)
    await waitFor(() => expect(screen.getByText(/40M\+/)).toBeInTheDocument())
    expect(screen.queryByText('sample')).not.toBeInTheDocument()
  })
})

describe('rate limiting', () => {
  it('shows the throttle message instead of the rephrase hint', async () => {
    mockRunQuery.mockResolvedValue({
      ...BASE,
      error: 'Rate limit reached (20 questions per hour).',
      rateLimited: true,
    })
    render(<Home />)
    fireEvent.change(screen.getByPlaceholderText(/average fare/i), {
      target: { value: 'How many trips?' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))

    await waitFor(() =>
      expect(screen.getByText(/rate limit reached/i)).toBeInTheDocument()
    )
    expect(screen.queryByText(/couldn't generate a valid query/i)).not.toBeInTheDocument()
  })

  it('still shows the rephrase hint for an ordinary query failure', async () => {
    mockRunQuery.mockResolvedValue({ ...BASE, error: 'Binder Error: no such column' })
    render(<Home />)
    fireEvent.change(screen.getByPlaceholderText(/average fare/i), {
      target: { value: 'nonsense' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))

    await waitFor(() =>
      expect(screen.getByText(/couldn't generate a valid query/i)).toBeInTheDocument()
    )
  })
})
