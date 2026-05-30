import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './contexts/AuthContext'
import Layout from './components/layout/Layout'
import Spinner from './components/ui/Spinner'

const Login = lazy(() => import('./pages/Login'))
const Dashboard = lazy(() => import('./pages/Dashboard'))
const Songs = lazy(() => import('./pages/Songs'))
const Browse = lazy(() => import('./pages/Browse'))
const ForYou = lazy(() => import('./pages/ForYou'))
const Playlists = lazy(() => import('./pages/Playlists'))
const Features = lazy(() => import('./pages/Features'))

function PageLoading() {
  return (
    <div className="min-h-screen flex items-center justify-center">
      <Spinner size="lg" />
    </div>
  )
}

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth()
  if (loading) return <PageLoading />
  if (!user) return <Navigate to="/login" replace />
  return <Layout>{children}</Layout>
}

export default function App() {
  return (
    <Suspense fallback={<PageLoading />}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/dashboard" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
        <Route path="/songs"     element={<ProtectedRoute><Songs /></ProtectedRoute>} />
        <Route path="/browse"    element={<ProtectedRoute><Browse /></ProtectedRoute>} />
        <Route path="/for-you"   element={<ProtectedRoute><ForYou /></ProtectedRoute>} />
        <Route path="/playlists" element={<ProtectedRoute><Playlists /></ProtectedRoute>} />
        <Route path="/features"  element={<ProtectedRoute><Features /></ProtectedRoute>} />
        <Route path="*"          element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </Suspense>
  )
}
