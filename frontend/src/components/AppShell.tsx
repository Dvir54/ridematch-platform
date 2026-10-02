import { Outlet, useLocation } from 'react-router-dom'
import { useCurrentUser } from '../auth/currentUserContext'
import { modeFromPath } from '../routes'
import { NotificationSocketProvider } from '../ws/NotificationSocketProvider'
import { BottomNav } from './BottomNav'
import { ModeSwitcher } from './ModeSwitcher'
import { Wordmark } from './Wordmark'

export function AppShell() {
  const user = useCurrentUser()
  const { pathname } = useLocation()
  const mode = modeFromPath(pathname, user.preferences.default_mode ?? 'passenger')

  return (
    <div className="min-h-dvh">
      <NotificationSocketProvider />
      <header className="border-b border-hairline bg-surface">
        <div className="mx-auto flex max-w-[34rem] items-center justify-between gap-4 px-5 py-3">
          <Wordmark />
          <ModeSwitcher mode={mode} />
        </div>
      </header>

      <main className="mx-auto w-full max-w-[34rem] px-5 pt-6 pb-28">
        <Outlet />
      </main>

      <BottomNav mode={mode} />
    </div>
  )
}
