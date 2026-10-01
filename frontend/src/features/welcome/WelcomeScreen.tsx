import { useAuth } from '@clerk/clerk-react'
import { Navigate } from 'react-router-dom'
import { ButtonLink } from '../../components/Button'
import { RouteRail } from '../../components/RouteRail'
import { Wordmark } from '../../components/Wordmark'

const steps = [
  'A driver posts the route and time they are already travelling.',
  'A passenger searches, finds the closest match and asks for a seat.',
  'The driver approves. You travel, then you rate each other.',
]

export function WelcomeScreen() {
  const { isLoaded, isSignedIn } = useAuth()
  if (isLoaded && isSignedIn) return <Navigate to="/app" replace />

  return (
    <div className="min-h-dvh px-5 py-6 sm:px-8">
      <header className="mx-auto flex max-w-5xl items-center justify-between">
        <Wordmark className="text-lg" />
      </header>

      <main className="mx-auto grid max-w-5xl gap-12 pt-10 pb-16 md:grid-cols-[minmax(0,1fr)_22rem] md:items-start md:gap-16 md:pt-16">
        <div className="max-w-[22ch] md:max-w-none">
          <h1 className="text-3xl md:text-[3rem]">Someone is already driving your route.</h1>
          <p className="mt-5 max-w-[52ch] text-lg text-ink-70">
            RideMatch puts drivers and passengers going the same way, at the same time, in the
            same car. Agree on a seat, split the cost, travel.
          </p>

          <div className="mt-8 flex flex-wrap gap-3">
            <ButtonLink to="/sign-up">Create account</ButtonLink>
            <ButtonLink to="/sign-in" variant="secondary">
              Sign in
            </ButtonLink>
          </div>

          <ol className="mt-12 space-y-4 border-t border-hairline pt-8">
            {steps.map((step, index) => (
              <li key={step} className="grid grid-cols-[1.75rem_1fr] gap-x-3">
                <span className="tnum text-sm font-semibold text-ink-45">{index + 1}</span>
                <p className="max-w-[56ch] text-ink-70">{step}</p>
              </li>
            ))}
          </ol>
        </div>

        <aside className="rounded-card border border-hairline bg-surface p-6 shadow-[0_1px_0_0_var(--color-hairline)] md:mt-2">
          <p className="text-sm font-semibold text-ink-45">Thursday, 08:15</p>
          <div className="mt-4">
            <RouteRail
              size="display"
              from="Dizengoff 50, Tel Aviv"
              fromDetail="Pickup at the corner"
              to="Ha-Nassi 12, Haifa"
              toDetail="3 seats free, 22 ILS each"
            />
          </div>
          <p className="mt-6 border-t border-hairline pt-4 text-sm text-ink-70">
            Noa drives this route most weekdays. 37 passengers have rated her 4.8.
          </p>
        </aside>
      </main>

      <footer className="mx-auto max-w-5xl border-t border-hairline pt-6 text-sm text-ink-70">
        Everyone on RideMatch is 18 or older and signs up with a verified email address.
      </footer>
    </div>
  )
}
