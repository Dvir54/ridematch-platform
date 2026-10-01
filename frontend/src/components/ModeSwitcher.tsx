import { useNavigate } from 'react-router-dom'
import { useUpdateMe } from '../api/hooks/users'
import type { Mode } from '../api/types'
import { homePathFor } from '../routes'

const LABELS: Record<Mode, string> = {
  driver: 'Driving',
  passenger: 'Riding',
}

/**
 * Switching mode changes the whole bottom nav, so it also becomes the user's
 * saved default — the app opens where they left off.
 */
export function ModeSwitcher({ mode }: { mode: Mode }) {
  const navigate = useNavigate()
  const updateMe = useUpdateMe()

  function switchTo(next: Mode) {
    if (next === mode) return
    navigate(homePathFor(next))
    updateMe.mutate({ preferences: { default_mode: next } })
  }

  return (
    <div
      role="group"
      aria-label="Travel mode"
      className="flex rounded-card border border-hairline bg-surface p-0.5"
    >
      {(['driver', 'passenger'] as const).map((option) => (
        <button
          key={option}
          type="button"
          aria-pressed={option === mode}
          onClick={() => switchTo(option)}
          className={`rounded-[0.25rem] px-3 py-1.5 text-sm font-semibold transition-colors ${
            option === mode ? 'bg-ink text-surface' : 'text-ink-70 hover:text-ink'
          }`}
        >
          {LABELS[option]}
        </button>
      ))}
    </div>
  )
}
