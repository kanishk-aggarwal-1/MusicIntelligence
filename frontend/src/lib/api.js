const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_URL
const BASE_URL = (configuredBaseUrl || (import.meta.env.DEV ? 'http://127.0.0.1:8000' : '')).replace(/\/$/, '')

async function request(path, options = {}) {
  if (!BASE_URL) {
    throw new Error('Missing VITE_API_BASE_URL. Set it to your Render backend URL and redeploy.')
  }

  const headers = { ...(options.headers || {}) }
  if (!(options.body instanceof FormData)) {
    headers['Content-Type'] = headers['Content-Type'] || 'application/json'
  }

  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers,
    credentials: 'include',
  })

  const text = await res.text()
  const data = text ? JSON.parse(text) : null

  if (!res.ok) {
    const message = data?.message || data?.detail || `HTTP ${res.status}`
    const lower = `${message} ${data?.detail || ''}`.toLowerCase()
    // Only fire auth-expired for true "not logged in" cases — not for
    // Spotify-specific token expiry (spotify_token_expired), which means the
    // user IS logged into the app but needs to reconnect Spotify.
    const isSpotifyTokenExpired = data?.detail === 'spotify_token_expired'
    if (!isSpotifyTokenExpired && (res.status === 401 || lower.includes('user not logged in'))) {
      window.dispatchEvent(new CustomEvent('musicintel:auth-expired', {
        detail: { status: res.status, message },
      }))
    }
    throw Object.assign(new Error(message), { status: res.status, data })
  }

  return data
}

export const api = {
  get: (path, params) => {
    const url = params ? `${path}?${new URLSearchParams(params)}` : path
    return request(url)
  },
  post: (path, body) =>
    request(path, { method: 'POST', body: body !== undefined ? JSON.stringify(body) : undefined }),
  patch: (path, body) =>
    request(path, { method: 'PATCH', body: body !== undefined ? JSON.stringify(body) : undefined }),
  delete: (path) => request(path, { method: 'DELETE' }),
  postForm: (path, formData) =>
    request(path, { method: 'POST', body: formData }),
  baseUrl: BASE_URL,
  configured: Boolean(BASE_URL),
}
