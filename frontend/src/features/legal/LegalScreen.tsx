import { Link } from 'react-router-dom'
import { Wordmark } from '../../components/Wordmark'
import { paths } from '../../routes'
import type { LegalDocument } from './legalContent'
import { PLACEHOLDER_NOTICE, PRIVACY, PRIVACY_CONTACT_EMAIL, TERMS } from './legalContent'

/** The privacy contact, or a visible placeholder until there is one. */
export function PrivacyContact() {
  if (!PRIVACY_CONTACT_EMAIL) {
    return <span className="font-medium text-alert">[privacy contact: to be provided]</span>
  }
  return (
    <a className="font-medium underline" href={`mailto:${PRIVACY_CONTACT_EMAIL}`}>
      {PRIVACY_CONTACT_EMAIL}
    </a>
  )
}

/** `/terms` and `/privacy` link pair, for footers. */
export function LegalLinks({ className = '' }: { className?: string }) {
  return (
    <nav aria-label="Legal" className={`flex flex-wrap gap-x-4 gap-y-1 ${className}`}>
      <Link className="underline" to={paths.terms}>
        Terms of Service
      </Link>
      <Link className="underline" to={paths.privacy}>
        Privacy Policy
      </Link>
    </nav>
  )
}

function LegalScreen({ document }: { document: LegalDocument }) {
  const placeholder = document.body.length === 0
  return (
    <div className="min-h-dvh px-5 py-6 sm:px-8">
      <header className="mx-auto flex max-w-3xl items-center justify-between">
        <Link to={paths.welcome} aria-label="RideMatch home">
          <Wordmark className="text-lg" />
        </Link>
      </header>

      <main className="mx-auto max-w-3xl pt-10 pb-16">
        <h1 className="text-3xl">{document.title}</h1>
        <p className="mt-2 text-sm text-ink-70">
          Effective date: {document.effectiveDate ?? '[to be provided]'}
        </p>

        {placeholder ? (
          <p role="note" className="mt-8 rounded-card border border-alert p-4 font-medium text-alert">
            {PLACEHOLDER_NOTICE}
          </p>
        ) : (
          <div className="mt-8 space-y-4">
            {document.body.map((paragraph) => (
              <p key={paragraph} className="max-w-[70ch] text-ink-70">
                {paragraph}
              </p>
            ))}
          </div>
        )}

        <p className="mt-8 text-sm text-ink-70">
          Privacy questions and deletion requests: <PrivacyContact />
        </p>
      </main>

      <footer className="mx-auto max-w-3xl border-t border-hairline pt-6 text-sm text-ink-70">
        <LegalLinks />
      </footer>
    </div>
  )
}

export function TermsScreen() {
  return <LegalScreen document={TERMS} />
}

export function PrivacyScreen() {
  return <LegalScreen document={PRIVACY} />
}
