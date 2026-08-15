import { fetchExamples, fetchSchema, runQuery, fetchHistory } from '@/lib/api'

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
  it('returns the columns and the dataset size', async () => {
    const cols = [{ name: 'VendorID', type: 'INTEGER' }]
    mockFetch.mockReturnValueOnce(mockOk({ columns: cols, row_count: 41_000_000 }))
    const result = await fetchSchema()
    expect(result).toEqual({ columns: cols, rowCount: 41_000_000 })
  })

  it('defaults the row count when an older backend omits it', async () => {
    mockFetch.mockReturnValueOnce(mockOk({ columns: [] }))
    expect((await fetchSchema()).rowCount).toBe(0)
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

  it('flags a throttled response so the UI can phrase it differently', async () => {
    mockFetch.mockReturnValueOnce(
      Promise.resolve({
        ok: false,
        status: 429,
        json: () => Promise.resolve({ error: 'Rate limit reached (20 questions per hour).' }),
      })
    )
    const result = await runQuery('How many trips?')
    expect(result.rateLimited).toBe(true)
    expect(result.error).toMatch(/rate limit/i)
  })

  it('does not flag ordinary errors as throttled', async () => {
    mockFetch.mockReturnValueOnce(
      Promise.resolve({ ok: false, status: 400, json: () => Promise.resolve({ error: 'bad' }) })
    )
    const result = await runQuery('bad question')
    expect(result.rateLimited).toBeUndefined()
  })

  it('passes through the cached and attempts fields', async () => {
    mockFetch.mockReturnValueOnce(mockOk({ ...MOCK_RESPONSE, cached: true, attempts: 2 }))
    const result = await runQuery('How many trips?')
    expect(result.cached).toBe(true)
    expect(result.attempts).toBe(2)
  })
})

// ---------------------------------------------------------------------------
// fetchHistory
// ---------------------------------------------------------------------------
describe('fetchHistory', () => {
  const MOCK_HISTORY = [
    {
      id: 1,
      question: 'How many trips?',
      sql: 'SELECT COUNT(*) FROM taxi',
      result: { columns: ['count_star()'], rows: [[5]], row_count: 1 },
      explanation: 'There were 5 trips.',
      latency_ms: 1200,
      created_at: '2024-01-01T10:00:00Z',
    },
  ]

  it('returns the history array', async () => {
    mockFetch.mockReturnValueOnce(mockOk({ history: MOCK_HISTORY }))
    const result = await fetchHistory()
    expect(result).toEqual(MOCK_HISTORY)
  })

  it('calls the correct URL', async () => {
    mockFetch.mockReturnValueOnce(mockOk({ history: [] }))
    await fetchHistory()
    expect(mockFetch).toHaveBeenCalledWith('http://localhost:8000/api/history')
  })

  it('throws on non-ok response', async () => {
    mockFetch.mockReturnValueOnce(mockFail())
    await expect(fetchHistory()).rejects.toThrow('Failed to fetch history')
  })
})
