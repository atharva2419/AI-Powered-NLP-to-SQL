/**
 * The API base URL is read from NEXT_PUBLIC_API_URL, which a human pastes
 * into a hosting dashboard. Browsers display URLs with a trailing slash, so
 * that is what gets pasted — and every call here appends "/api/...", giving
 * "https://host//api/query". Starlette matches routes exactly, so a doubled
 * slash is a 404 rather than a redirect.
 */

const ORIGINAL = process.env.NEXT_PUBLIC_API_URL

async function loadApiWith(baseUrl: string | undefined) {
  jest.resetModules()
  if (baseUrl === undefined) delete process.env.NEXT_PUBLIC_API_URL
  else process.env.NEXT_PUBLIC_API_URL = baseUrl
  return import('@/lib/api')
}

afterEach(() => {
  if (ORIGINAL === undefined) delete process.env.NEXT_PUBLIC_API_URL
  else process.env.NEXT_PUBLIC_API_URL = ORIGINAL
  jest.resetModules()
})

function mockOnce(mockFetch: jest.Mock) {
  mockFetch.mockReturnValueOnce(
    Promise.resolve({ ok: true, json: () => Promise.resolve({ examples: [] }) })
  )
}

describe('API base URL', () => {
  it('strips a trailing slash', async () => {
    const mockFetch = jest.fn()
    global.fetch = mockFetch
    const api = await loadApiWith('https://api.example.com/')
    mockOnce(mockFetch)

    await api.fetchExamples()
    expect(mockFetch).toHaveBeenCalledWith('https://api.example.com/api/examples')
  })

  it('strips several trailing slashes', async () => {
    const mockFetch = jest.fn()
    global.fetch = mockFetch
    const api = await loadApiWith('https://api.example.com///')
    mockOnce(mockFetch)

    await api.fetchExamples()
    expect(mockFetch).toHaveBeenCalledWith('https://api.example.com/api/examples')
  })

  it('leaves a clean URL alone', async () => {
    const mockFetch = jest.fn()
    global.fetch = mockFetch
    const api = await loadApiWith('https://api.example.com')
    mockOnce(mockFetch)

    await api.fetchExamples()
    expect(mockFetch).toHaveBeenCalledWith('https://api.example.com/api/examples')
  })

  it('falls back to localhost when unset', async () => {
    const mockFetch = jest.fn()
    global.fetch = mockFetch
    const api = await loadApiWith(undefined)
    mockOnce(mockFetch)

    await api.fetchExamples()
    expect(mockFetch).toHaveBeenCalledWith('http://localhost:8000/api/examples')
  })
})
