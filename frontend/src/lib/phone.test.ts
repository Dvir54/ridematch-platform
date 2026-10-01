import { describe, expect, it } from 'vitest'
import { isValidPhone } from './phone'

describe('phone format', () => {
  it.each(['+972 50-123-4567', '050-123-4567', '0501234567', '+1 555 010 9999'])(
    'accepts %s',
    (value) => {
      expect(isValidPhone(value)).toBe(true)
    },
  )

  it.each([
    ['+1 (555) 010-9999', 'parentheses'],
    ['+1.555.0199', 'dots'],
    ['abc', 'letters'],
    ['12345', 'too short'],
    ['1'.repeat(21), 'too long'],
  ])('rejects %s (%s)', (value) => {
    expect(isValidPhone(value)).toBe(false)
  })
})
