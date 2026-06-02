import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { api } from './api'

function mockFetchOnce({ ok, status, body }) {
  global.fetch = vi.fn().mockResolvedValue({
    ok,
    status,
    text: async () => (body == null ? '' : JSON.stringify(body)),
  })
}

describe('api request layer', () => {
  let authEvents
  let handler

  beforeEach(() => {
    authEvents = []
    handler = (e) => authEvents.push(e.detail)
    window.addEventListener('musicintel:auth-expired', handler)
  })

  afterEach(() => {
    window.removeEventListener('musicintel:auth-expired', handler)
    vi.restoreAllMocks()
  })

  it('returns parsed JSON on success', async () => {
    mockFetchOnce({ ok: true, status: 200, body: { hello: 'world' } })
    await expect(api.get('/x')).resolves.toEqual({ hello: 'world' })
  })

  it('sends credentials and a JSON content-type on POST', async () => {
    mockFetchOnce({ ok: true, status: 200, body: {} })
    await api.post('/y', { a: 1 })
    const [url, opts] = global.fetch.mock.calls[0]
    expect(url).toBe('http://test.local/y')
    expect(opts.credentials).toBe('include')
    expect(opts.headers['Content-Type']).toBe('application/json')
    expect(opts.body).toBe(JSON.stringify({ a: 1 }))
  })

  it('does not set JSON content-type for FormData bodies', async () => {
    mockFetchOnce({ ok: true, status: 200, body: {} })
    await api.postForm('/upload', new FormData())
    const [, opts] = global.fetch.mock.calls[0]
    expect(opts.headers['Content-Type']).toBeUndefined()
  })

  it('throws an error carrying status and data on failure', async () => {
    mockFetchOnce({ ok: false, status: 500, body: { detail: 'boom' } })
    await expect(api.get('/x')).rejects.toMatchObject({
      status: 500,
      data: { detail: 'boom' },
    })
  })

  it('dispatches auth-expired on a plain 401', async () => {
    mockFetchOnce({ ok: false, status: 401, body: { detail: 'User not logged in' } })
    await expect(api.get('/x')).rejects.toBeTruthy()
    expect(authEvents).toHaveLength(1)
    expect(authEvents[0].status).toBe(401)
  })

  it('does NOT dispatch auth-expired when the Spotify token expired', async () => {
    // The user is still logged into the app; only the Spotify grant lapsed.
    mockFetchOnce({ ok: false, status: 401, body: { detail: 'spotify_token_expired' } })
    await expect(api.get('/x')).rejects.toBeTruthy()
    expect(authEvents).toHaveLength(0)
  })
})
