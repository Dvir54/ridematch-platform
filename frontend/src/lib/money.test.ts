import { describe, expect, it } from 'vitest'
import { formatMoney, formatMoneyTotal, isValidMoney, toMoney } from './money'

describe('money', () => {
  it('accepts the shapes a person types and normalises them to two places', () => {
    expect(toMoney('25')).toBe('25.00')
    expect(toMoney('25.5')).toBe('25.50')
    expect(toMoney(' 25.50 ')).toBe('25.50')
    expect(toMoney('0')).toBe('0.00')
  })

  it('refuses anything the contract would answer 422 for', () => {
    // Money is `^\d{1,8}(\.\d{1,2})?$` in openapi.yaml — no signs, no thousands,
    // no third decimal, and never a float dressed up as text.
    for (const bad of ['', 'free', '-5', '25.505', '1,000', '25.', '1e3']) {
      expect(isValidMoney(bad), bad).toBe(false)
      expect(toMoney(bad), bad).toBeNull()
    }
  })

  it('formats a price and a multi-seat total', () => {
    expect(formatMoney('25.50')).toBe('₪25.50')
    expect(formatMoney('18')).toBe('₪18.00')
    expect(formatMoneyTotal('25.50', 3)).toBe('₪76.50')
    expect(formatMoneyTotal('25.50', 1)).toBe('₪25.50')
  })
})
