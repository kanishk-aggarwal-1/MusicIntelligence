import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './contexts/AuthContext'
import Layout from './components/layout/Layout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Songs from './pages/Songs'
import Playlists from './pages/Playlists'
import Features from './pages/Features'
import Browse from './pages/Browse'
import Spinner from './components/ui/Spinner'

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth()
  if (loading) return (
    <div className="min-h-screen flex items-center justify-center">
      <Spinner size="lg" />
    </div>
  )
  if (!user) return <Navigate to="/login" replace />
  return <Layout>{children}</Layout>
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/dashboard" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
      <Route path="/songs"     element={<ProtectedRoute><Songs /></ProtectedRoute>} />
      <Route path="/playlists" element={<ProtectedRoute><Playlists /></ProtectedRoute>} />
      <Route path="/features"  element={<ProtectedRoute><Features /></ProtectedRoute>} />
      <Route path="/browse"    element={<ProtectedRoute><Browse /></ProtectedRoute>} />
      <Route path="*"          element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}
