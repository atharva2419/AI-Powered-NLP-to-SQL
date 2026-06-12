import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import Home from '@/app/page'
import * as api from '@/lib/api'

// Mock heavy syntax highlighter — not relevant to UI behaviour tests
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

// Mock the recharts-based chart — SVG charts don't render in jsdom.
// Chart detection logic is tested separately in chart.test.ts.
jest.mock('@/components/ResultChart', () => ({
  __esModule: true,
  default: ({ columns, rows }: { columns: string[]; rows: unknown[][] }) => (
    <div data-testid="result-chart" data-columns={columns.join(',')} data-rows={rows.length} />
  ),
}))

jest.mock('@/lib/api')
const mockFetchExamples = api.fetchExamples as jest.MockedFunction<typeof api.fetchExamples>
const mockFetchSchema   = api.fetchSchema   as jest.MockedFunction<typeof api.fetchSchema>
const mockRunQuery      = api.runQuery      as jest.MockedFunction<typeof api.runQuery>
const mockFetchHistory  = api.fetchHistory  as jest.MockedFunction<typeof api.fetchHistory>

const EXAMPLES = ['How many trips?', 'What is the average fare?']
const SCHEMA   = [{ name: 'fare_amount', type: 'DOUBLE' }, { name: 'VendorID', type: 'INTEGER' }]
const SUCCESS_RESULT: api.QueryResponse = {
  sql: 'SELECT COUNT(*) FROM taxi',
  result: { columns: ['count_star()'], rows: [[5]], row_count: 1 },
  explanation: 'There were 5 trips in total.',
  latency_ms: 1500,
}

beforeEach(() => {
  mockFetchExamples.mockResolvedValue(EXAMPLES)
  mockFetchSchema.mockResolvedValue(SCHEMA)
  mockRunQuery.mockResolvedValue(SUCCESS_RESULT)
  mockFetchHistory.mockResolvedValue([])
})

afterEach(() => jest.clearAllMocks())

// ---------------------------------------------------------------------------
describe('layout', () => {
  it('renders the page heading', () => {
    render(<Home />)
    expect(screen.getByText('NYC Taxi Explorer')).toBeInTheDocument()
  })

  it('renders the search input and Ask button', () => {
    render(<Home />)
    expect(screen.getByPlaceholderText(/average fare/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ask' })).toBeInTheDocument()
  })

  it('Ask button is disabled when input is empty', () => {
    render(<Home />)
    expect(screen.getByRole('button', { name: 'Ask' })).toBeDisabled()
  })
})

// ---------------------------------------------------------------------------
describe('example chips', () => {
  it('renders chips fetched from the API', async () => {
    render(<Home />)
    await waitFor(() => expect(screen.getByText('How many trips?')).toBeInTheDocument())
    expect(screen.getByText('What is the average fare?')).toBeInTheDocument()
  })

  it('clicking a chip fills the input', async () => {
    render(<Home />)
    await waitFor(() => screen.getByText('How many trips?'))
    fireEvent.click(screen.getByText('How many trips?'))
    expect(screen.getByDisplayValue('How many trips?')).toBeInTheDocument()
  })

  it('clicking a chip submits the query', async () => {
    render(<Home />)
    await waitFor(() => screen.getByText('How many trips?'))
    fireEvent.click(screen.getByText('How many trips?'))
    await waitFor(() => expect(mockRunQuery).toHaveBeenCalledWith('How many trips?'))
  })
})

// ---------------------------------------------------------------------------
describe('successful query', () => {
  async function submitQuery() {
    render(<Home />)
    await waitFor(() => screen.getByText('How many trips?'))
    fireEvent.click(screen.getByText('How many trips?'))
    await waitFor(() => screen.getByTestId('sql-block'))
  }

  it('shows the generated SQL', async () => {
    await submitQuery()
    expect(screen.getByTestId('sql-block')).toHaveTextContent('SELECT COUNT(*) FROM taxi')
  })

  it('shows the plain-English explanation', async () => {
    await submitQuery()
    expect(screen.getByText('There were 5 trips in total.')).toBeInTheDocument()
  })

  it('shows latency in seconds', async () => {
    await submitQuery()
    expect(screen.getByText(/Answered in 1\.5s/)).toBeInTheDocument()
  })

  it('renders the chart with the result data', async () => {
    await submitQuery()
    const chart = screen.getByTestId('result-chart')
    expect(chart).toHaveAttribute('data-columns', 'count_star()')
    expect(chart).toHaveAttribute('data-rows', '1')
  })
})

// ---------------------------------------------------------------------------
describe('error handling', () => {
  it('shows friendly message on API error', async () => {
    mockRunQuery.mockResolvedValueOnce({ ...SUCCESS_RESULT, error: 'Query blocked' })
    render(<Home />)
    await waitFor(() => screen.getByText('How many trips?'))
    fireEvent.click(screen.getByText('How many trips?'))
    await waitFor(() =>
      expect(screen.getByText(/couldn't generate a valid query/i)).toBeInTheDocument()
    )
  })

  it('shows technical reason below the friendly message', async () => {
    mockRunQuery.mockResolvedValueOnce({ ...SUCCESS_RESULT, error: 'DROP is not allowed' })
    render(<Home />)
    await waitFor(() => screen.getByText('How many trips?'))
    fireEvent.click(screen.getByText('How many trips?'))
    await waitFor(() => expect(screen.getByText('DROP is not allowed')).toBeInTheDocument())
  })

  it('shows network error when server is unreachable', async () => {
    mockRunQuery.mockRejectedValueOnce(new Error('fetch failed'))
    render(<Home />)
    const input = screen.getByPlaceholderText(/average fare/i)
    fireEvent.change(input, { target: { value: 'test question' } })
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))
    await waitFor(() =>
      expect(screen.getByText(/Could not reach the server/)).toBeInTheDocument()
    )
  })
})

// ---------------------------------------------------------------------------
describe('schema sidebar', () => {
  it('shows the Schema toggle after schema loads', async () => {
    render(<Home />)
    await waitFor(() => expect(screen.getByText('Schema')).toBeInTheDocument())
  })

  it('clicking Schema toggle reveals column names', async () => {
    render(<Home />)
    await waitFor(() => screen.getByText('Schema'))
    fireEvent.click(screen.getByText('Schema'))
    expect(screen.getByText('fare_amount')).toBeInTheDocument()
    expect(screen.getByText('VendorID')).toBeInTheDocument()
  })

  it('clicking Schema toggle again hides columns', async () => {
    render(<Home />)
    await waitFor(() => screen.getByText('Schema'))
    fireEvent.click(screen.getByText('Schema'))
    fireEvent.click(screen.getByText('Schema'))
    expect(screen.queryByText('fare_amount')).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
describe('query history', () => {
  const HISTORY_ITEM: api.HistoryItem = {
    id: 1,
    question: 'Saved question',
    sql: 'SELECT AVG(fare_amount) FROM taxi',
    result: { columns: ['avg'], rows: [[14.2]], row_count: 1 },
    explanation: 'Average fare was $14.20.',
    latency_ms: 800,
    created_at: new Date().toISOString(),
  }

  it('shows Recent queries heading when history is non-empty', async () => {
    mockFetchHistory.mockResolvedValue([HISTORY_ITEM])
    render(<Home />)
    await waitFor(() => expect(screen.getByText('Recent queries')).toBeInTheDocument())
  })

  it('does not show Recent queries when history is empty', async () => {
    mockFetchHistory.mockResolvedValue([])
    render(<Home />)
    await waitFor(() => screen.getByText('How many trips?'))
    expect(screen.queryByText('Recent queries')).not.toBeInTheDocument()
  })

  it('clicking a history item restores the question in the input', async () => {
    mockFetchHistory.mockResolvedValue([HISTORY_ITEM])
    render(<Home />)
    await waitFor(() => screen.getByText('Saved question'))
    fireEvent.click(screen.getByText('Saved question'))
    expect(screen.getByDisplayValue('Saved question')).toBeInTheDocument()
  })

  it('clicking a history item shows the saved SQL without calling runQuery', async () => {
    mockFetchHistory.mockResolvedValue([HISTORY_ITEM])
    render(<Home />)
    await waitFor(() => screen.getByText('Saved question'))
    fireEvent.click(screen.getByText('Saved question'))
    await waitFor(() =>
      expect(screen.getByTestId('sql-block')).toHaveTextContent('SELECT AVG(fare_amount) FROM taxi')
    )
    expect(mockRunQuery).not.toHaveBeenCalled()
  })
})
