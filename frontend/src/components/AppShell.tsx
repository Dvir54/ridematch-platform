import { useEffect, useRef } from 'react'
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
  const main = useRef<HTMLElement>(null)
  const firstRender = useRef(true)

  // A client-side route change leaves focus on the old link; move it to the new page so screen
  // reader and keyboard users start from the top of the content.
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false
      return
    }
    main.current?.focus()
  }, [pathname])

  return (
    <div className="min-h-dvh">
      <NotificationSocketProvider />
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:m-2 focus:bg-ink focus:px-4 focus:py-2 focus:text-surface"
      >
        Skip to content
      </a>
      <header className="border-b border-hairline bg-surface">
        <div className="mx-auto flex max-w-[34rem] items-center justify-between gap-4 px-5 py-3">
          <Wordmark />
          <ModeSwitcher mode={mode} />
        </div>
      </header>

      <main
        id="main"
        ref={main}
        tabIndex={-1}
        className="mx-auto w-full max-w-[34rem] px-5 pt-6 pb-28 outline-none"
      >
        <Outlet />
      </main>

      <BottomNav mode={mode} />
    </div>
  )
}
