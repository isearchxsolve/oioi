import { Routes, Route } from 'react-router-dom'
import { Sidebar } from '@/components/layout/Sidebar'
import { Header } from '@/components/layout/Header'
import { Dashboard } from '@/pages/Dashboard'
import { ScriptGenerator } from '@/pages/ScriptGenerator'
import { VideoGenerator } from '@/pages/VideoGenerator'
import { Projects } from '@/pages/Projects'
import { Settings } from '@/pages/Settings'
import { useUIStore } from '@/stores/uiStore'

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

function App() {
  return <Layout />
}

export default App