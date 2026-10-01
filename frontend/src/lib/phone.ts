/**
 * The one phone rule, mirroring the `Phone` primitive in openapi.yaml:
 * digits, spaces, hyphens, dots and brackets, with an optional leading `+`.
 * Every form that sends `phone` validates through here, so the onboarding and
 * profile paths cannot drift apart.
 *
 * The server stores whatever is typed, character for character — it does not
 * normalise phone numbers the way it does plates.
 */
export const PHONE_PATTERN = /^\+?[0-9 ().-]{7,20}$/

export const PHONE_HINT = 'Use digits, spaces, brackets, dots or hyphens, 7 to 20 characters.'

export function isValidPhone(value: string): boolean {
  return PHONE_PATTERN.test(value.trim())
}
