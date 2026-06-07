import { Menu, LogOut, User } from 'lucide-react'
import { useAuth } from '@/context/AuthContext'

interface NavbarProps {
  onMenuClick: () => void
  title: string
}

export function Navbar({ onMenuClick, title }: NavbarProps) {
  const { user, logout } = useAuth()

  return (
    <header className="h-16 bg-white border-b border-slate-200 flex items-center px-4 gap-4 sticky top-0 z-10">
      <button
        onClick={onMenuClick}
        className="lg:hidden p-2 text-slate-500 hover:text-slate-700 rounded-lg hover:bg-slate-100"
      >
        <Menu className="w-5 h-5" />
      </button>

      <h1 className="font-semibold text-slate-800 text-[15px] flex-1">{title}</h1>

      <div className="flex items-center gap-3">
        <div className="hidden sm:flex items-center gap-2">
          <div className="w-8 h-8 bg-green-100 rounded-full flex items-center justify-center">
            <User className="w-4 h-4 text-green-700" />
          </div>
          <span className="text-sm font-medium text-slate-700">{user?.full_name}</span>
        </div>
        <button
          onClick={logout}
          className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-red-600
                     px-3 py-1.5 rounded-lg hover:bg-red-50 transition-colors"
        >
          <LogOut className="w-4 h-4" />
          <span className="hidden sm:inline">Logout</span>
        </button>
      </div>
    </header>
  )
}
