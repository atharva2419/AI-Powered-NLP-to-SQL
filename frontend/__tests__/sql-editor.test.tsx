/**
 * The SQL editor turns the query from a receipt into a tool: edit it, run it,
 * see what changed. These cover the parts that are easy to get subtly wrong —
 * chiefly that the UI never presents the model's explanation next to somebody
 * else's numbers.
 */
import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import Home from '@/app/page'
import * as api from '@/lib/api'

// The real highlighter pulls in ESM-only deps that jest will not transform,
// and its styled spans are irrelevant here — only the edit/run flow matters.
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
  default: ({ columns }: { columns: string[] }) => (
    <div data-testid="result-chart" data-columns={columns.join(',')} />
  ),
}))

jest.mock('@/lib/api')
const mockFetchExamples = api.fetchExamples as jest.MockedFunction<typeof api.fetchExamples>
const mockFetchSchema = api.fetchSchema as jest.MockedFunction<typeof api.fetchSchema>
const mockRunQuery = api.runQuery as jest.MockedFunction<typeof api.runQuery>
const mockFetchHistory = api.fetchHistory as jest.MockedFunction<typeof api.fetchHistory>
const mockExecuteSql = api.executeSql as jest.MockedFunction<typeof api.executeSql>

const ANSWER: api.QueryResponse = {
  sql: 'SELECT COUNT(*) AS trips FROM taxi',
  result: { columns: ['trips'], rows: [[41000000]], row_count: 1 },
  explanation: 'There were 41 million trips.',
  latency_ms: 1500,
}

beforeEach(() => {
  // clearAllMocks, not just re-stubbing: call counts otherwise accumulate
  // across tests and "was the LLM called once?" silently becomes meaningless.
  jest.clearAllMocks()
  mockFetchExamples.mockResolvedValue([])
  mockFetchSchema.mockResolvedValue({ columns: [], rowCount: 41_000_000 })
  mockFetchHistory.mockResolvedValue([])
  mockRunQuery.mockResolvedValue(ANSWER)
})

async function askAQuestion() {
  render(<Home />)
  fireEvent.change(screen.getByPlaceholderText(/average fare/i), {
    target: { value: 'how many trips?' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Ask' }))
  await waitFor(() => expect(screen.getByText('Edit')).toBeInTheDocument())
}

async function startEditing() {
  await askAQuestion()
  fireEvent.click(screen.getByText('Edit'))
  return screen.getByLabelText('Edit SQL query') as HTMLTextAreaElement
}

describe('entering edit mode', () => {
  it('shows the generated SQL in an editable field', async () => {
    const textarea = await startEditing()
    expect(textarea.value).toBe(ANSWER.sql)
  })

  it('offers Run and Cancel instead of Edit and Copy', async () => {
    await startEditing()
    expect(screen.getByText(/Run/)).toBeInTheDocument()
    expect(screen.getByText('Cancel')).toBeInTheDocument()
    expect(screen.queryByText('Edit')).not.toBeInTheDocument()
  })

  it('discards the draft on Cancel', async () => {
    const textarea = await startEditing()
    fireEvent.change(textarea, { target: { value: 'SELECT 1' } })
    fireEvent.click(screen.getByText('Cancel'))

    fireEvent.click(screen.getByText('Edit'))
    expect((screen.getByLabelText('Edit SQL query') as HTMLTextAreaElement).value).toBe(ANSWER.sql)
  })

  it('discards the draft on Escape', async () => {
    const textarea = await startEditing()
    fireEvent.change(textarea, { target: { value: 'SELECT 1' } })
    fireEvent.keyDown(textarea, { key: 'Escape' })
    expect(screen.queryByLabelText('Edit SQL query')).not.toBeInTheDocument()
  })
})

describe('running edited SQL', () => {
  const EDITED = 'SELECT payment_type, COUNT(*) AS n FROM taxi GROUP BY payment_type'
  const EDITED_RESULT: api.ExecuteResponse = {
    sql: EDITED,
    result: { columns: ['payment_type', 'n'], rows: [[1, 30], [2, 5]], row_count: 2 },
    latency_ms: 120,
  }

  async function runEdited(response: api.ExecuteResponse = EDITED_RESULT) {
    mockExecuteSql.mockResolvedValue(response)
    const textarea = await startEditing()
    fireEvent.change(textarea, { target: { value: EDITED } })
    fireEvent.click(screen.getByText(/Run/))
    return textarea
  }

  it('sends the edited SQL to the execute endpoint', async () => {
    await runEdited()
    await waitFor(() => expect(mockExecuteSql).toHaveBeenCalledWith(EDITED))
  })

  it('does not spend an LLM call', async () => {
    await runEdited()
    await waitFor(() => expect(mockExecuteSql).toHaveBeenCalled())
    expect(mockRunQuery).toHaveBeenCalledTimes(1) // only the original question
  })

  it('updates the results table', async () => {
    await runEdited()
    await waitFor(() => expect(screen.getByText('Payment type')).toBeInTheDocument())
    expect(screen.getByText('Credit card')).toBeInTheDocument()
  })

  it('updates the chart', async () => {
    await runEdited()
    await waitFor(() =>
      expect(screen.getByTestId('result-chart')).toHaveAttribute(
        'data-columns',
        'payment_type,n'
      )
    )
  })

  it('hides the explanation, which described the old query', async () => {
    await askAQuestion()
    expect(screen.getByText(ANSWER.explanation)).toBeInTheDocument()

    mockExecuteSql.mockResolvedValue(EDITED_RESULT)
    fireEvent.click(screen.getByText('Edit'))
    fireEvent.change(screen.getByLabelText('Edit SQL query'), { target: { value: EDITED } })
    fireEvent.click(screen.getByText(/Run/))

    await waitFor(() => expect(screen.queryByText(ANSWER.explanation)).not.toBeInTheDocument())
  })

  it('marks the results as the user’s own', async () => {
    await runEdited()
    await waitFor(() => expect(screen.getByText('your query')).toBeInTheDocument())
    expect(screen.getByText('edited')).toBeInTheDocument()
  })

  it('runs on Ctrl+Enter', async () => {
    mockExecuteSql.mockResolvedValue(EDITED_RESULT)
    const textarea = await startEditing()
    fireEvent.change(textarea, { target: { value: EDITED } })
    fireEvent.keyDown(textarea, { key: 'Enter', ctrlKey: true })
    await waitFor(() => expect(mockExecuteSql).toHaveBeenCalledWith(EDITED))
  })
})

describe('when the edited SQL is bad', () => {
  it('shows the database error and keeps the previous results', async () => {
    mockExecuteSql.mockResolvedValue({
      sql: 'SELECT nope FROM taxi',
      result: { columns: [], rows: [], row_count: 0 },
      latency_ms: 5,
      error: 'Binder Error: Referenced column "nope" not found',
    })
    const textarea = await startEditing()
    fireEvent.change(textarea, { target: { value: 'SELECT nope FROM taxi' } })
    fireEvent.click(screen.getByText(/Run/))

    await waitFor(() => expect(screen.getByText(/Referenced column/)).toBeInTheDocument())
    // The old answer is still on screen to compare against.
    expect(screen.getByText('41,000,000')).toBeInTheDocument()
  })

  it('reports a rejected query from the SQL guard', async () => {
    mockExecuteSql.mockResolvedValue({
      sql: 'DROP TABLE taxi',
      result: { columns: [], rows: [], row_count: 0 },
      latency_ms: 1,
      error: 'Only SELECT queries are permitted; this is a DROP statement.',
    })
    const textarea = await startEditing()
    fireEvent.change(textarea, { target: { value: 'DROP TABLE taxi' } })
    fireEvent.click(screen.getByText(/Run/))

    await waitFor(() => expect(screen.getByText(/Only SELECT queries/)).toBeInTheDocument())
  })
})

describe('asking a new question after editing', () => {
  it('clears the edited state', async () => {
    mockExecuteSql.mockResolvedValue({
      sql: 'SELECT 1 AS a FROM taxi',
      result: { columns: ['a'], rows: [[1]], row_count: 1 },
      latency_ms: 10,
    })
    const textarea = await startEditing()
    fireEvent.change(textarea, { target: { value: 'SELECT 1 AS a FROM taxi' } })
    fireEvent.click(screen.getByText(/Run/))
    await waitFor(() => expect(screen.getByText('edited')).toBeInTheDocument())

    fireEvent.change(screen.getByPlaceholderText(/average fare/i), {
      target: { value: 'something else' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))

    await waitFor(() => expect(screen.queryByText('edited')).not.toBeInTheDocument())
    expect(screen.getByText(ANSWER.explanation)).toBeInTheDocument()
  })
})
