import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import { api } from '../lib/api'
import Spinner from '../components/ui/Spinner'

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const configError = !api.configured

  async function handleLogin() {
    if (configError) return
    setLoading(true)
    setError(null)
    try {
      await login()
      navigate('/dashboard')
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-zinc-950 flex items-center justify-center p-6">
      <div className="w-full max-w-sm text-center space-y-8">
        <div className="space-y-3">
          <div className="w-16 h-16 rounded-full bg-brand/10 border border-brand/30 flex items-center justify-center mx-auto text-3xl">
            ♪
          </div>
          <h1 className="text-3xl font-bold text-white">MusicIntelligence</h1>
          <p className="text-zinc-400 text-sm leading-relaxed">
            AI-powered playlists built from your actual listening history.
            Connect Spotify to get started.
          </p>
        </div>

        <button
          onClick={handleLogin}
          disabled={loading || configError}
          className="w-full flex items-center justify-center gap-3 px-6 py-3.5 rounded-xl bg-brand text-black font-semibold text-sm hover:bg-green-400 transition-colors disabled:opacity-60"
        >
          {loading ? (
            <Spinner size="sm" />
          ) : (
            <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 0C5.4 0 0 5.4 0 12s5.4 12 12 12 12-5.4 12-12S18.66 0 12 0zm5.521 17.34c-.24.359-.66.48-1.021.24-2.82-1.74-6.36-2.101-10.561-1.141-.418.122-.779-.179-.899-.539-.12-.421.18-.78.54-.9 4.56-1.021 8.52-.6 11.64 1.32.42.18.479.659.301 1.02zm1.44-3.3c-.301.42-.841.6-1.262.3-3.239-1.98-8.159-2.58-11.939-1.38-.479.12-1.02-.12-1.14-.6-.12-.48.12-1.021.6-1.141C9.6 9.9 15 10.561 18.72 12.84c.361.181.54.78.241 1.2zm.12-3.36C15.24 8.4 8.82 8.16 5.16 9.301c-.6.179-1.2-.181-1.38-.721-.18-.601.18-1.2.72-1.381 4.26-1.26 11.28-1.02 15.721 1.621.539.3.719 1.02.419 1.56-.299.421-1.02.599-1.559.3z" />
            </svg>
          )}
          {loading ? 'Opening Spotify...' : 'Connect with Spotify'}
        </button>

        {configError && (
          <p className="text-red-400 text-sm bg-red-400/10 rounded-lg px-4 py-2.5">
            Missing VITE_API_BASE_URL. Set it to your Render backend URL in Vercel and redeploy.
          </p>
        )}

        {error && (
          <p className="text-red-400 text-sm bg-red-400/10 rounded-lg px-4 py-2.5">{error}</p>
        )}

        <p className="text-zinc-600 text-xs">
          Your data stays in your own database. Nothing is shared.
        </p>
      </div>
    </div>
  )
}
