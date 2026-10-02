import { isApiError } from './errors'

/**
 * A 422's `details` sorted into the inputs that caused them.
 *
 * `details[].field` names the most specific location the server can attribute the
 * failure to, and contract 0.4.5 says it may get **more** specific in a later
 * version without that being a breaking change. So a form must do two things: map
 * the fields it recognises onto its controls, and keep somewhere to show a field it
 * cannot place. A form that only does the first silently drops the reason the
 * moment the server gets more precise — which is exactly how the ride form and the
 * onboarding form both broke.
 *
 * `owners` maps a server field name — with or without the `body.` prefix — to the
 * control that should show it. Several names may share one control: an address
 * picker owns its address and both coordinates, because nobody edits a latitude by
 * hand. Anything unmapped comes back in `rest`, which the caller must render.
 */
export function collectFieldErrors<K extends string>(
  error: unknown,
  owners: Record<string, K>,
): { fields: Partial<Record<K, string>>; rest: string[] } {
  if (!isApiError(error)) return { fields: {}, rest: [] }

  const fields: Partial<Record<K, string>> = {}
  const rest: string[] = []

  for (const detail of error.details) {
    const name = detail.field.replace(/^body\./, '')
    // The first message for a control wins: later ones would overwrite a more
    // specific complaint with a vaguer one about the same input.
    const owner = owners[name]
    if (owner) fields[owner] ??= detail.message
    else rest.push(detail.message)
  }

  return { fields, rest }
}
