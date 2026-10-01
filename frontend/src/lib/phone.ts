/**
 * The one phone rule, mirroring the `Phone` primitive in openapi.yaml:
 * digits, spaces and hyphens, with an optional leading `+`. No parentheses,
 * no dots. Every form that sends `phone` validates through here, so the
 * onboarding and profile paths cannot drift apart.
 */
export const PHONE_PATTERN = /^\+?[0-9 -]{7,20}$/

export const PHONE_HINT = 'Use digits, spaces and hyphens, 7 to 20 characters.'

export function isValidPhone(value: string): boolean {
  return PHONE_PATTERN.test(value.trim())
}
