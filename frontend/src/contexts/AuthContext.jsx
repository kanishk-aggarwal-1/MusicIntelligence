import { createContext, useContext, useEffect, useState } from 'react'
import { api } from '../lib/api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get('/user/session')
      .then(d => setUser(d.logged_in ? d : null))
      .catch(() => setUser(null))
      .finally(() => setLoading(false))
  }, [])

  async function login() {
    try { await api.post('/user/logout') } catch {}

    const popup = window.open(
      `${api.baseUrl}/user/login`,
      'spotify_login',
      'width=520,height=740'
    )
    if (!popup) throw new Error('Popup blocked — allow popups for this site and try again.')

    return new Promise((resolve, reject) => {
      const start = Date.now()
      const timer = setInterval(async () => {
        try {
          if (Date.now() - start > 120_000) {
            clearInterval(timer)
            popup.close()
            return reject(new Error('Login timed out.'))
          }
          if (popup.closed) {
            clearInterval(timer)
            const s = await api.get('/user/session')
            if (s.logged_in) { setUser(s); resolve(s) }
            else reject(new Error('Login window closed before authentication completed.'))
            return
          }
          const s = await api.get('/user/session')
          if (s.logged_in) {
            clearInterval(timer)
            popup.close()
            setUser(s)
            resolve(s)
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
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
