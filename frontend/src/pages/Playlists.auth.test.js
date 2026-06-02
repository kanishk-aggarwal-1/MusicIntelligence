import { describe, it, expect } from 'vitest'
import { isSpotifyTokenExpired, isLoggedOutError } from './Playlists'

describe('playlist auth-error predicates', () => {
  it('detects an expired Spotify token from the error detail', () => {
    expect(isSpotifyTokenExpired({ data: { detail: 'spotify_token_expired' } })).toBe(true)
    expect(isSpotifyTokenExpired({ data: { detail: 'something else' } })).toBe(false)
    expect(isSpotifyTokenExpired({})).toBe(false)
  })

  it('does not treat an expired Spotify token as a full logout', () => {
    // Critical: otherwise the user gets bounced to /login and loses their preview.
    expect(isLoggedOutError({ status: 401, data: { detail: 'spotify_token_expired' } })).toBe(false)
  })

  it('treats a plain 401 as logged out', () => {
    expect(isLoggedOutError({ status: 401, data: { detail: 'User not logged in' } })).toBe(true)
  })

  it('detects logout from message text without a status', () => {
    expect(isLoggedOutError({ message: 'User not logged in' })).toBe(true)
  })

  it('returns false for unrelated errors', () => {
    expect(isLoggedOutError({ status: 500, data: { detail: 'database_error' } })).toBe(false)
  })
})
