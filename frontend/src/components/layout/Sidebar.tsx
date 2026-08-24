import { NavLink, useLocation } from 'react-router-dom'
import { useUIStore } from '@/stores/uiStore'
import { cn } from '@/lib/utils'
import {
  LayoutDashboard,
  FileText,
  Video,
  FolderOpen,
  Settings,
  ChevronLeft,
  ChevronRight,
  Sparkles,
} from 'lucide-react'

const navigation = [
  { name: 'Dashboard', href: '/', icon: LayoutDashboard },
  { name: 'Script Generator', href: '/script-generator', icon: FileText },
  { name: 'Video Generator', href: '/video-generator', icon: Video },
  { name: 'Projects', href: '/projects', icon: FolderOpen },
  { name: 'Settings', href: '/settings', icon: Settings },
]

export function Sidebar() {
  const { sidebarOpen, toggleSidebar } = useUIStore()
  const location = useLocation()
  
  return (
    <aside
      className={cn(
        'fixed left-0 top-0 z-40 h-screen bg-white border-r border-dark-200 dark:bg-dark-900 dark:border-dark-700 transition-all duration-300',
        sidebarOpen ? 'w-64 lg:w-64' : 'w-20 lg:w-20'
      )}
    >
      <div className="flex h-full flex-col">
        {/* Logo */}
        <div className="flex h-16 items-center justify-between px-4 border-b border-dark-200 dark:border-dark-700">
          <NavLink to="/" className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary-600">
              <Sparkles className="h-5 w-5 text-white" />
            </div>
            {sidebarOpen && (
              <span className="font-bold text-xl text-dark-900 dark:text-white">Film Kit</span>
            )}
          </NavLink>
          <button
            onClick={toggleSidebar}
            className={cn(
              'p-1.5 rounded-lg text-dark-500 hover:bg-dark-100 dark:text-dark-400 dark:hover:bg-dark-800',
              sidebarOpen ? 'lg:hidden' : 'hidden'
            )}
            aria-label={sidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'}
          >
            {sidebarOpen ? <ChevronLeft className="h-5 w-5" /> : <ChevronRight className="h-5 w-5" />}
          </button>
        </div>
        
        {/* Navigation */}
        <nav className="flex-1 space-y-1 p-3 overflow-y-auto" aria-label="Main navigation">
          {navigation.map((item) => {
            const Icon = item.icon
            const isActive = location.pathname === item.href || 
              (item.href !== '/' && location.pathname.startsWith(item.href))
            
            return (
              <NavLink
                key={item.name}
                to={item.href}
                className={({ isActive }) => cn(
                  'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-primary-50 text-primary-700 dark:bg-primary-900/20 dark:text-primary-300'
                    : 'text-dark-600 hover:bg-dark-100 dark:text-dark-400 dark:hover:bg-dark-800',
                  !sidebarOpen && 'justify-center'
                )}
                title={sidebarOpen ? undefined : item.name}
              >
                <Icon className="h-5 w-5 flex-shrink-0" aria-hidden="true" />
                {sidebarOpen && <span className="truncate">{item.name}</span>}
              </NavLink>
            )
          })}
        </nav>
        
        {/* Footer */}
        <div className="p-3 border-t border-dark-200 dark:border-dark-700">
          <div className={cn('flex items-center gap-3', !sidebarOpen && 'justify-center')}>
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary-100 dark:bg-primary-900/30">
              <Sparkles className="h-4 w-4 text-primary-600 dark:text-primary-400" />
            </div>
            {sidebarOpen && (
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium text-dark-900 dark:text-white truncate">Powered by NVIDIA NIM</p>
                <p className="text-xs text-dark-500 dark:text-dark-400 truncate">AI Video Generation</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </aside>
  )
}