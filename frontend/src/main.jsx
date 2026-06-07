import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { AuthProvider } from './contexts/AuthContext'
import { PlayerProvider } from './contexts/PlayerContext'
import './index.css'

// After a new Vercel deploy, lazy-loaded chunk filenames change.  Any user
// still on the old page gets a 404 HTML response when the browser tries to
// fetch the old chunk → MIME type error → blank screen.
// Reloading fetches the latest index.html and the new chunk URLs.
window.addEventListener('vite:preloadError', () => {
  window.location.reload()
})

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <PlayerProvider>
          <App />
        </PlayerProvider>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>
)
