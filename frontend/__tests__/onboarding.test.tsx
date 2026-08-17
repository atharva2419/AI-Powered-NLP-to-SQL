/**
 * What a first-time visitor sees before they have asked anything.
 *
 * The hosted backend sleeps when idle, so the very first load often lands
 * while the server is still waking. Before this, that produced a page with a
 * heading, an empty text box and nothing else — no examples, no glossary, no
 * explanation of what the thing is or why it looked broken.
 */
import React from 'react'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
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
jest.mock('@/components/SqlEditor', () => ({
  __esModule: true,
  default: () => <div data-testid="sql-editor" />,
}))

jest.mock('@/lib/api')
const mockFetchExamples = api.fetchExamples as jest.MockedFunction<typeof api.fetchExamples>
const mockFetchSchema = api.fetchSchema as jest.MockedFunction<typeof api.fetchSchema>
const mockRunQuery = api.runQuery as jest.MockedFunction<typeof api.runQuery>
const mockFetchHistory = api.fetchHistory as jest.MockedFunction<typeof api.fetchHistory>

const EXAMPLES = ['How many trips were taken in total?', 'What is the average fare from JFK Airport?']
const SCHEMA = {
  columns: [
    { name: 'fare_amount', type: 'DOUBLE' },
    { name: 'pickup_zone', type: 'VARCHAR' },
  ],
  rowCount: 1_000_000,
}

beforeEach(() => {
  // Clear call counts *and* implementations, then re-establish defaults —
  // otherwise counts accumulate across cases in this file.
  jest.clearAllMocks()
  mockFetchExamples.mockResolvedValue(EXAMPLES)
  mockFetchSchema.mockResolvedValue(SCHEMA)
  mockFetchHistory.mockResolvedValue([])
  mockRunQuery.mockReset()
})

describe('explaining what the app is', () => {
  // Copy is deliberately non-technical — this is a first stop for hiring
  // managers and other non-engineers, not a spec. No "SQL", "DuckDB" or
  // "language model" in the pitch; those live in the README instead.
  it('says it is about exploring NYC taxi rides', async () => {
    render(<Home />)
    expect(screen.getByText(/new york city taxi rides/i)).toBeInTheDocument()
  })

  it('says questions can be asked in plain English', async () => {
    render(<Home />)
    // Mentioned in both the header subtitle and the intro paragraph.
    expect(screen.getAllByText(/plain english/i).length).toBeGreaterThan(0)
  })

  it('avoids technical jargon in the pitch', async () => {
    render(<Home />)
    expect(screen.queryByText(/language model/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/DuckDB/i)).not.toBeInTheDocument()
  })

  it('shows the intro even while the backend is still waking', async () => {
    mockFetchExamples.mockRejectedValue(new Error('offline'))
    mockFetchSchema.mockRejectedValue(new Error('offline'))
    render(<Home />)
    // The description is static copy, so a sleeping backend must not hide it.
    expect(screen.getByText(/new york city taxi rides/i)).toBeInTheDocument()
  })
})

describe('first-visit orientation panel', () => {
  it('walks through ask, see the answer, dig deeper', async () => {
    render(<Home />)
    await waitFor(() => expect(screen.getByText('Ask')).toBeInTheDocument())
    expect(screen.getByText('See the answer')).toBeInTheDocument()
    expect(screen.getByText('Dig deeper')).toBeInTheDocument()
  })

  it('summarises what the dataset covers', async () => {
    render(<Home />)
    await waitFor(() => expect(screen.getByText(/Jan–Dec 2024/)).toBeInTheDocument())
    expect(screen.getByText(/265 pickup & dropoff zones/i)).toBeInTheDocument()
    expect(screen.getByText(/Fares, tips, distances/i)).toBeInTheDocument()
  })

  it('reports the live column count rather than a hardcoded one', async () => {
    render(<Home />)
    const facts = await screen.findByTestId('dataset-facts')
    expect(within(facts).getByText('2')).toBeInTheDocument()
    expect(facts).toHaveTextContent('columns')
  })

  it('labels the example chips so they read as suggestions', async () => {
    render(<Home />)
    await waitFor(() => expect(screen.getByText('Try:')).toBeInTheDocument())
  })

  it('gets out of the way once there is a result', async () => {
    mockRunQuery.mockResolvedValue({
      sql: 'SELECT COUNT(*) FROM taxi',
      result: { columns: ['n'], rows: [[5]], row_count: 1 },
      explanation: 'Five trips.',
      latency_ms: 100,
    })
    render(<Home />)
    await waitFor(() => expect(screen.getByText('See the answer')).toBeInTheDocument())

    fireEvent.click(screen.getByText(EXAMPLES[0]))

    // SqlEditor is mocked in this file, so the editor stands in for the result.
    await waitFor(() => expect(screen.getByTestId('sql-editor')).toBeInTheDocument())
    expect(screen.queryByText('See the answer')).not.toBeInTheDocument()
    expect(screen.queryByText('Try:')).not.toBeInTheDocument()
  })

  it('stays hidden while the backend is unreachable', async () => {
    mockFetchExamples.mockRejectedValue(new Error('offline'))
    mockFetchSchema.mockRejectedValue(new Error('offline'))
    render(<Home />)
    // Quoting "265 zones" over a backend we cannot reach would be a guess.
    await waitFor(() => expect(screen.getByText(/can't reach the query service/i)).toBeInTheDocument())
    expect(screen.queryByText('See the answer')).not.toBeInTheDocument()
  })
})

describe('cold start', () => {
  it('explains the wait instead of showing an empty page', async () => {
    // Never resolves: the state a visitor lands in while Render wakes up.
    mockFetchExamples.mockReturnValue(new Promise(() => {}))
    mockFetchSchema.mockReturnValue(new Promise(() => {}))
    render(<Home />)
    expect(screen.getByText(/waking the server/i)).toBeInTheDocument()
    expect(screen.getByText(/up to a minute/i)).toBeInTheDocument()
  })

  it('offers a retry when the backend is unreachable', async () => {
    mockFetchExamples.mockRejectedValue(new Error('offline'))
    mockFetchSchema.mockRejectedValue(new Error('offline'))
    render(<Home />)

    const retry = await screen.findByRole('button', { name: /try again/i })
    expect(mockFetchExamples).toHaveBeenCalledTimes(1)

    mockFetchExamples.mockResolvedValue(EXAMPLES)
    mockFetchSchema.mockResolvedValue(SCHEMA)
    fireEvent.click(retry)

    await waitFor(() => expect(screen.getByText(EXAMPLES[0])).toBeInTheDocument())
    expect(screen.queryByText(/can't reach the query service/i)).not.toBeInTheDocument()
  })

  it('does not report offline when only the optional history call fails', async () => {
    mockFetchHistory.mockRejectedValue(new Error('history is down'))
    render(<Home />)
    await waitFor(() => expect(screen.getByText(EXAMPLES[0])).toBeInTheDocument())
    expect(screen.queryByText(/can't reach the query service/i)).not.toBeInTheDocument()
  })
})
