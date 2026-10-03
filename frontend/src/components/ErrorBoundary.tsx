import { Component, type ErrorInfo, type ReactNode } from 'react'
import { reportError } from '../monitoring'
import { MessageScreen } from './states'

interface State {
  failed: boolean
}

/** Last line of defence: a render crash shows a way back instead of a blank page. */
export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { failed: false }

  static getDerivedStateFromError(): State {
    return { failed: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Unhandled render error', error, info.componentStack)
    reportError(error, info.componentStack)
  }

  render() {
    if (!this.state.failed) return this.props.children
    return (
      <MessageScreen
        title="Something went wrong"
        body="The page hit an error it could not recover from. Reloading usually fixes it."
        action={
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="rounded-card bg-ink px-5 py-3 text-sm font-semibold text-surface"
          >
            Reload
          </button>
        }
      />
    )
  }
}
