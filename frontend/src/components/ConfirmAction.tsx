import { useState } from 'react'
import { Button } from './Button'

export interface ConfirmActionProps {
  /** The quiet button that opens the question. */
  label: string
  /** What actually happens, in one sentence. Written before the decision. */
  question: string
  confirmLabel: string
  onConfirm: () => void
  pending?: boolean
  disabled?: boolean
}

/**
 * Cancelling a ride tells real people their plans are off, so it is never one
 * tap. The question appears inline rather than in a browser dialog, which keeps
 * the consequence on screen next to the button that causes it.
 */
export function ConfirmAction({
  label,
  question,
  confirmLabel,
  onConfirm,
  pending,
  disabled,
}: ConfirmActionProps) {
  const [asking, setAsking] = useState(false)

  if (!asking) {
    return (
      <Button variant="secondary" disabled={disabled || pending} onClick={() => setAsking(true)}>
        {label}
      </Button>
    )
  }

  return (
    <div className="rounded-card border border-alert/30 bg-alert-wash p-4">
      <p className="text-sm font-medium text-alert">{question}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button variant="secondary" disabled={pending} onClick={onConfirm}>
          {pending ? 'Working…' : confirmLabel}
        </Button>
        <Button variant="quiet" disabled={pending} onClick={() => setAsking(false)}>
          Keep it
        </Button>
      </div>
    </div>
  )
}
