import { useEffect, useState } from 'react'
import { Navigate, Routes, Route } from 'react-router-dom'
import { Sidebar } from '@/components/layout/Sidebar'
import { Header } from '@/components/layout/Header'
import { Dashboard } from '@/pages/Dashboard'
import { ScriptGenerator } from '@/pages/ScriptGenerator'
import { VideoGenerator } from '@/pages/VideoGenerator'
import { Projects } from '@/pages/Projects'
import { Settings } from '@/pages/Settings'
import { useUIStore } from '@/stores/uiStore'
import { api } from '@/lib/api'
import { Login } from '@/pages/Login'

function Layout() {
  const { sidebarOpen, toggleSidebar } = useUIStore()
  
  return (
    <div className="min-h-screen bg-dark-50 dark:bg-dark-950">
      <Sidebar />
      <div
        className={`transition-all duration-300 min-h-screen ${
          sidebarOpen ? 'lg:pl-64' : 'lg:pl-20'
        }`}
      >
        <Header onMenuClick={toggleSidebar} />
        <main className="p-6 lg:p-8">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/script-generator" element={<ScriptGenerator />} />
            <Route path="/video-generator" element={<VideoGenerator />} />
            <Route path="/projects" element={<Projects />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </main>
      </div>
    </div>
  )
}

function RequireAuthentication({ children }: { children: React.ReactNode }) {
  const [checking, setChecking] = useState(true)
  const [allowed, setAllowed] = useState(false)

  useEffect(() => {
    if (!api.isAuthenticated()) {
      setChecking(false)
      return
    }
    api.getCurrentUser().then(() => setAllowed(true)).catch(() => api.clearTokens()).finally(() => setChecking(false))
  }, [])

  if (checking) return <main className="min-h-screen bg-dark-950 p-8 text-dark-300">Checking studio access…</main>
  return allowed ? <>{children}</> : <Navigate to="/login" replace />
}

function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/*" element={<RequireAuthentication><Layout /></RequireAuthentication>} />
    </Routes>
  )
}

export default App
