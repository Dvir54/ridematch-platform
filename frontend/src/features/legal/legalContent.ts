/**
 * PLACEHOLDERS. The Terms of Service and Privacy Policy text, their effective
 * dates and the privacy contact come from Dvir; nothing here is legal text.
 * Replace each value below before launch (PRODUCTION_READINESS_PLAN.md §12).
 */
export const PLACEHOLDER_NOTICE =
  'Placeholder: this document has not been written yet. It must be replaced before launch.'

export interface LegalDocument {
  title: string
  /** `null` until the real document exists. */
  effectiveDate: string | null
  /** Paragraphs; empty until the real text exists. */
  body: string[]
}

export const TERMS: LegalDocument = {
  title: 'Terms of Service',
  effectiveDate: null,
  body: [],
}

export const PRIVACY: LegalDocument = {
  title: 'Privacy Policy',
  effectiveDate: null,
  body: [],
}

/** Where people send privacy and data-deletion requests. `null` until Dvir provides it. */
export const PRIVACY_CONTACT_EMAIL: string | null = null
