import { describe, expect, it } from 'vitest'
import { backoffDelay } from './backoff'

describe('backoffDelay', () => {
  it('doubles each attempt, capped at 30s', () => {
    expect(backoffDelay(0)).toBe(1_000)
    expect(backoffDelay(1)).toBe(2_000)
    expect(backoffDelay(2)).toBe(4_000)
    expect(backoffDelay(5)).toBe(30_000)
    expect(backoffDelay(10)).toBe(30_000)
  })
})
