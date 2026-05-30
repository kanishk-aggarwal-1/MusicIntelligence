import { createContext, useContext, useEffect, useState } from 'react'
import { api } from '../lib/api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [serverWarming, setServerWarming] = useState(false)

  useEffect(() => {
    // If the first call takes more than 5 s the Render instance is cold-starting.
    const warmTimer = setTimeout(() => setServerWarming(true), 5000)
    api.get('/user/session')
      .then(d => setUser(d.logged_in ? d : null))
      .catch(() => setUser(null))
      .finally(() => {
        clearTimeout(warmTimer)
        setServerWarming(false)
        setLoading(false)
      })
    return () => clearTimeout(warmTimer)
  }, [])

  async function login() {
    try { await api.post('/user/logout') } catch {}

    const frontendOrigin = encodeURIComponent(window.location.origin)
    const popup = window.open(
      `${api.baseUrl}/user/login?frontend_origin=${frontendOrigin}`,
      'spotify_login',
      'width=520,height=740'
    )
    if (!popup) throw new Error('Popup blocked. Allow popups for this site and try again.')

    return new Promise((resolve, reject) => {
      const start = Date.now()
      let settled = false

      const finish = (callback, value) => {
        if (settled) return
        settled = true
        clearInterval(timer)
        window.removeEventListener('message', onMessage)
        callback(value)
      }

      const completeLogin = async () => {
        const s = await api.get('/user/session')
        if (!s.logged_in) {
          throw new Error('Login completed, but the session cookie was not found.')
        }
        popup.close()
        setUser(s)
        finish(resolve, s)
      }

      const onMessage = (event) => {
        if (event.source !== popup) return
        if (event.data?.type === 'musicintel:login-error') {
          popup.close()
          finish(reject, new Error(event.data?.message || 'Spotify login failed.'))
          return
        }
        if (event.data?.type === 'musicintel:login-success') {
          completeLogin().catch(err => finish(reject, err))
        }
      }

      window.addEventListener('message', onMessage)

      const timer = setInterval(async () => {
        try {
          if (Date.now() - start > 120_000) {
            popup.close()
            return finish(reject, new Error('Login timed out.'))
          }

          if (popup.closed) {
            const s = await api.get('/user/session')
            if (s.logged_in) {
              setUser(s)
              finish(resolve, s)
            } else {
              finish(reject, new Error('Login window closed before authentication completed.'))
            }
            return
          }

          const s = await api.get('/user/session')
          if (s.logged_in) {
            popup.close()
            setUser(s)
            finish(resolve, s)
          }
        } catch {}
      }, 1000)
    })
  }

  async function logout() {
    await api.post('/user/logout')
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, loading, serverWarming, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
