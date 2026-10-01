import type { ReactNode } from 'react'

/** Shown while Clerk or the first `GET /users/me` is still resolving. */
export function FullScreenLoader({ label = 'Loading' }: { label?: string }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex min-h-dvh flex-col items-center justify-center gap-4 px-6"
    >
      <span className="flex gap-1.5" aria-hidden="true">
        <span className="size-2 animate-pulse bg-ink" />
        <span className="size-2 animate-pulse bg-ink/60 [animation-delay:150ms]" />
        <span className="size-0 border-x-[0.3rem] border-t-[0.45rem] border-x-transparent border-t-signal-deep" />
      </span>
      <p className="text-sm text-ink-70">{label}</p>
    </div>
  )
}

/** An error inside a form or a card. Says what happened; never apologises. */
export function ErrorNotice({ children }: { children: ReactNode }) {
  return (
    <p
      role="alert"
      className="rounded-card border border-alert/30 bg-alert-wash px-4 py-3 text-sm font-medium text-alert"
    >
      {children}
    </p>
  )
}

export interface MessageScreenProps {
  title: string
  body: string
  action?: ReactNode
}

/** A whole screen that cannot show its content — empty, blocked or broken. */
export function MessageScreen({ title, body, action }: MessageScreenProps) {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-5 px-6 text-center">
      <div className="max-w-[34ch] space-y-3">
        <h1 className="text-xl">{title}</h1>
        <p className="text-ink-70">{body}</p>
      </div>
      {action}
    </div>
  )
}

/** An empty tab inside the shell: says what will live here and how to fill it. */
export function EmptyState({ title, body, action }: MessageScreenProps) {
  return (
    <div className="flex flex-col items-start gap-4 rounded-card border border-dashed border-hairline bg-surface/60 px-5 py-8">
      <div className="max-w-[40ch] space-y-2">
        <h2 className="text-lg">{title}</h2>
        <p className="text-sm text-ink-70">{body}</p>
      </div>
      {action}
    </div>
  )
}

/** Missing VITE_* configuration — a developer problem, said plainly. */
export function ConfigurationNeeded({ variable }: { variable: string }) {
  return (
    <MessageScreen
      title="RideMatch is not configured yet"
      body={`Set ${variable} in the .env file at the repo root, then restart the dev server.`}
    />
  )
}
