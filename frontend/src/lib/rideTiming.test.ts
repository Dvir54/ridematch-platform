import { describe, expect, it } from 'vitest'
import { shortAddress } from './address'
import {
  canCancelApprovedYet,
  canStartYet,
  dateTimeLocalToIso,
  isoToDateTimeLocal,
} from './dates'

const departure = new Date('2026-10-08T09:00:00Z')
const at = (minutesBefore: number) => new Date(departure.getTime() - minutesBefore * 60_000)

describe('start cutoff', () => {
  it('opens exactly two hours before departure (CONTRACT §3)', () => {
    expect(canStartYet(departure.toISOString(), at(121))).toBe(false)
    expect(canStartYet(departure.toISOString(), at(120))).toBe(true)
    expect(canStartYet(departure.toISOString(), at(1))).toBe(true)
    expect(canStartYet(departure.toISOString(), at(-30))).toBe(true)
  })
})

describe('approved-seat cancel cutoff', () => {
  it('closes exactly one hour before departure (D15)', () => {
    expect(canCancelApprovedYet(departure.toISOString(), at(61))).toBe(true)
    // At the cutoff itself the seat is already locked.
    expect(canCancelApprovedYet(departure.toISOString(), at(60))).toBe(false)
    expect(canCancelApprovedYet(departure.toISOString(), at(0))).toBe(false)
  })
})

describe('datetime-local round trip', () => {
  it('returns the same instant it was given', () => {
    const iso = '2026-10-08T09:00:00.000Z'
    expect(dateTimeLocalToIso(isoToDateTimeLocal(iso))).toBe(iso)
  })

  it('answers null for an empty or unparsable field', () => {
    expect(dateTimeLocalToIso('')).toBeNull()
    expect(dateTimeLocalToIso('not a time')).toBeNull()
  })
})

describe('shortAddress', () => {
  it('keeps the street and the town and drops the country', () => {
    expect(shortAddress('Rothschild Boulevard 1, Tel Aviv-Yafo, Israel')).toBe(
      'Rothschild Boulevard 1, Tel Aviv-Yafo',
    )
    expect(shortAddress('Haifa, Israel')).toBe('Haifa, Israel')
    expect(shortAddress('Haifa')).toBe('Haifa')
  })
})
