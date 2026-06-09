import { fetchExamples, fetchSchema, runQuery } from '@/lib/api'

const mockFetch = jest.fn()
global.fetch = mockFetch

beforeEach(() => mockFetch.mockClear())

function mockOk(body: unknown) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve(body) })
}

function mockFail() {
  return Promise.resolve({ ok: false })
}

// ---------------------------------------------------------------------------
// fetchExamples
// ---------------------------------------------------------------------------
describe('fetchExamples', () => {
  it('returns the examples array', async () => {
    mockFetch.mockReturnValueOnce(mockOk({ examples: ['How many trips?', 'Avg fare?'] }))
    const result = await fetchExamples()
    expect(result).toEqual(['How many trips?', 'Avg fare?'])
  })

  it('calls the correct URL', async () => {
    mockFetch.mockReturnValueOnce(mockOk({ examples: [] }))
    await fetchExamples()
    expect(mockFetch).toHaveBeenCalledWith('http://localhost:8000/api/examples')
  })

  it('throws on non-ok response', async () => {
    mockFetch.mockReturnValueOnce(mockFail())
    await expect(fetchExamples()).rejects.toThrow('Failed to fetch examples')
  })
})

// ---------------------------------------------------------------------------
// fetchSchema
// ---------------------------------------------------------------------------
describe('fetchSchema', () => {
  it('returns the columns array', async () => {
    const cols = [{ name: 'VendorID', type: 'INTEGER' }]
    mockFetch.mockReturnValueOnce(mockOk({ columns: cols }))
    const result = await fetchSchema()
    expect(result).toEqual(cols)
  })

  it('throws on non-ok response', async () => {
    mockFetch.mockReturnValueOnce(mockFail())
    await expect(fetchSchema()).rejects.toThrow('Failed to fetch schema')
  })
})

// ---------------------------------------------------------------------------
// runQuery
// ---------------------------------------------------------------------------
describe('runQuery', () => {
  const MOCK_RESPONSE = {
    sql: 'SELECT COUNT(*) FROM taxi',
    result: { columns: ['count_star()'], rows: [[5]], row_count: 1 },
    explanation: 'There were 5 trips.',
    latency_ms: 1200,
  }

  it('returns the parsed response', async () => {
    mockFetch.mockReturnValueOnce(mockOk(MOCK_RESPONSE))
    const result = await runQuery('How many trips?')
    expect(result).toEqual(MOCK_RESPONSE)
  })

  it('posts to the correct URL with JSON body', async () => {
    mockFetch.mockReturnValueOnce(mockOk(MOCK_RESPONSE))
    await runQuery('How many trips?')
    expect(mockFetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/query',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: 'How many trips?' }),
      })
    )
  })

  it('returns error shape on API error response', async () => {
    mockFetch.mockReturnValueOnce(mockOk({ error: 'Query failed' }))
    const result = await runQuery('bad question')
    expect(result.error).toBe('Query failed')
  })
})
