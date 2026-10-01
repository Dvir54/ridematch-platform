import type { Money } from '../api/types'

/**
 * Money crosses the wire as a decimal **string** with 2 places (CONTRACT §2),
 * never a float — so it is parsed only to be displayed, and the value the form
 * sends is built back into a string.
 */
const MONEY_PATTERN = /^\d{1,8}(\.\d{1,2})?$/

/**
 * No currency field exists in the contract, and payment happens off-app
 * (scope G2). The symbol is cosmetic and lives here alone.
 */
const SYMBOL = '₪'

export const MONEY_HINT = 'A price like 25 or 25.50, up to two decimals.'

export function isValidMoney(raw: string): boolean {
  return MONEY_PATTERN.test(raw.trim())
}

/** Form text → the contract's `Money`, or null when it is not a price. */
export function toMoney(raw: string): Money | null {
  const trimmed = raw.trim()
  if (!isValidMoney(trimmed)) return null
  return Number(trimmed).toFixed(2)
}

export function formatMoney(value: Money): string {
  const amount = Number(value)
  if (!Number.isFinite(amount)) return `${SYMBOL}${value}`
  return `${SYMBOL}${amount.toFixed(2)}`
}

/** "₪25.50 · 3 seats" style total, for a request of more than one seat. */
export function formatMoneyTotal(pricePerSeat: Money, seats: number): string {
  const amount = Number(pricePerSeat)
  if (!Number.isFinite(amount)) return formatMoney(pricePerSeat)
  return `${SYMBOL}${(amount * seats).toFixed(2)}`
}
