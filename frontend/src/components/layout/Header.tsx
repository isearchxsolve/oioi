import { useUIStore } from '@/stores/uiStore'
import { cn } from '@/lib/utils'
import { Menu, Sun, Moon, Monitor, Bell, User, LogOut, ChevronDown } from 'lucide-react'
import { useState, useRef, useEffect } from 'react'

export function Header({ onMenuClick }: { onMenuClick: () => void }) {
  const { theme, setTheme } = useUIStore()
  const [userMenuOpen, setUserMenuOpen] = useState(false)
  const [notificationsOpen, setNotificationsOpen] = useState(false)
  const userMenuRef = useRef<HTMLDivElement>(null)
  const notificationsRef = useRef<HTMLDivElement>(null)
  
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (userMenuRef.current && !userMenuRef.current.contains(event.target as Node)) {
        setUserMenuOpen(false)
      }
      if (notificationsRef.current && !notificationsRef.current.contains(event.target as Node)) {
        setNotificationsOpen(false)
      }
    }
    
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])
  
  const toggleTheme = () => {
    const themes: ('light' | 'dark' | 'system')[] = ['light', 'dark', 'system']
    const currentIndex = themes.indexOf(theme)
    setTheme(themes[(currentIndex + 1) % themes.length])
  }
  
  const getThemeIcon = () => {
    switch (theme) {
      case 'light': return <Sun className="h-5 w-5" />
      case 'dark': return <Moon className="h-5 w-5" />
      default: return <Monitor className="h-5 w-5" />
    }
  }
  
  const getThemeLabel = () => {
    switch (theme) {
      case 'light': return 'Light'
      case 'dark': return 'Dark'
      default: return 'System'
    }
  }
  
  return (
    <header className="sticky top-0 z-30 h-16 bg-white/80 backdrop-blur-sm border-b border-dark-200 dark:bg-dark-900/80 dark:border-dark-700">
      <div className="flex h-full items-center justify-between px-4 lg:px-6">
        {/* Left side - Menu button */}
        <div className="flex items-center gap-4">
          <button
            onClick={onMenuClick}
            className="lg:hidden p-2 rounded-lg text-dark-500 hover:bg-dark-100 dark:text-dark-400 dark:hover:bg-dark-800"
            aria-label="Toggle menu"
          >
            <Menu className="h-6 w-6" />
          </button>
          
          {/* Search */}
          <div className="hidden sm:block">
            <div className="relative">
              <input
                type="search"
                placeholder="Search projects, scripts, videos..."
                className="w-64 sm:w-80 pl-10 pr-4 py-2 text-sm bg-dark-50 border border-dark-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent dark:bg-dark-800 dark:border-dark-700 dark:text-white"
              />
              <svg className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-dark-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </div>
          </div>
        </div>
        
        {/* Right side - Actions */}
        <div className="flex items-center gap-2">
          {/* Theme Toggle */}
          <button
            onClick={toggleTheme}
            className="p-2 rounded-lg text-dark-500 hover:bg-dark-100 dark:text-dark-400 dark:hover:bg-dark-800"
            aria-label={`Current theme: ${getThemeLabel()}. Click to change.`}
            title={`Theme: ${getThemeLabel()}`}
          >
            {getThemeIcon()}
          </button>
          
          {/* Notifications */}
          <div className="relative" ref={notificationsRef}>
            <button
              onClick={() => setNotificationsOpen(!notificationsOpen)}
              className="p-2 rounded-lg text-dark-500 hover:bg-dark-100 dark:text-dark-400 dark:hover:bg-dark-800 relative"
              aria-label="Notifications"
              aria-expanded={notificationsOpen}
            >
              <Bell className="h-5 w-5" />
              <span className="absolute top-1 right-1 h-2 w-2 rounded-full bg-red-500" />
            </button>
            
            {notificationsOpen && (
              <div className="absolute right-0 mt-2 w-80 bg-white rounded-xl border border-dark-200 shadow-lg dark:bg-dark-900 dark:border-dark-700 py-2">
                <div className="px-4 py-2 border-b border-dark-200 dark:border-dark-700">
                  <h3 className="font-semibold text-dark-900 dark:text-white">Notifications</h3>
                </div>
                <div className="max-h-64 overflow-y-auto">
                  <div className="px-4 py-3 text-center text-dark-500 dark:text-dark-400 text-sm">
                    No notifications yet
                  </div>
                </div>
                <div className="px-4 py-2 border-t border-dark-200 dark:border-dark-700">
                  <button className="text-sm text-primary-600 hover:text-primary-700 dark:text-primary-400 w-full text-left">
                    View all notifications
                  </button>
                </div>
              </div>
            )}
          </div>
          
          {/* User Menu */}
          <div className="relative" ref={userMenuRef}>
            <button
              onClick={() => setUserMenuOpen(!userMenuOpen)}
              className="flex items-center gap-2 p-1.5 rounded-lg hover:bg-dark-100 dark:hover:bg-dark-800"
              aria-label="User menu"
              aria-expanded={userMenuOpen}
            >
              <div className="h-8 w-8 rounded-full bg-primary-100 dark:bg-primary-900/30 flex items-center justify-center">
                <User className="h-5 w-5 text-primary-600 dark:text-primary-400" />
              </div>
              <span className="hidden md:block text-sm font-medium text-dark-700 dark:text-dark-300">User</span>
              <ChevronDown className="h-4 w-4 text-dark-500 hidden md:block" />
            </button>
            
            {userMenuOpen && (
              <div className="absolute right-0 mt-2 w-48 bg-white rounded-xl border border-dark-200 shadow-lg dark:bg-dark-900 dark:border-dark-700 py-2">
                <div className="px-4 py-2 border-b border-dark-200 dark:border-dark-700">
                  <p className="font-medium text-dark-900 dark:text-white">John Doe</p>
                  <p className="text-sm text-dark-500 dark:text-dark-400">john@example.com</p>
                </div>
                <button className="w-full px-4 py-2 text-left text-sm text-dark-700 dark:text-dark-300 hover:bg-dark-100 dark:hover:bg-dark-800 flex items-center gap-2">
                  <User className="h-4 w-4" />
                  Profile
                </button>
                <button className="w-full px-4 py-2 text-left text-sm text-dark-700 dark:text-dark-300 hover:bg-dark-100 dark:hover:bg-dark-800 flex items-center gap-2">
                  <Settings className="h-4 w-4" />
                  Settings
                </button>
                <hr className="my-2 border-dark-200 dark:border-dark-700" />
                <button className="w-full px-4 py-2 text-left text-sm text-red-600 dark:text-red-400 hover:bg-dark-100 dark:hover:bg-dark-800 flex items-center gap-2">
                  <LogOut className="h-4 w-4" />
                  Sign out
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  )
}

// Need to import Settings icon
import { Settings } from 'lucide-react'