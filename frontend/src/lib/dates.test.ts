import { describe, expect, it } from 'vitest'
import { isAdult, todayAsDateInput, yearsOld } from './dates'

const TODAY = new Date('2026-10-01T09:00:00')

describe('age checks', () => {
  it('counts whole years', () => {
    expect(yearsOld('1996-02-11', TODAY)).toBe(30)
  })

  it('accepts someone turning 18 today', () => {
    expect(isAdult('2008-10-01', TODAY)).toBe(true)
  })

  it('rejects someone one day short of 18', () => {
    expect(isAdult('2008-10-02', TODAY)).toBe(false)
  })

  it('rejects an unparsable date', () => {
    expect(isAdult('', TODAY)).toBe(false)
  })

  it('offers today as the latest selectable birth date', () => {
    expect(todayAsDateInput(TODAY)).toBe('2026-10-01')
  })
})
