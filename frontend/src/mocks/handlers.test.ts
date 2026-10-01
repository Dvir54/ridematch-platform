import { describe, expect, it } from 'vitest'
import { api } from '../api/client'
import type { ApiError } from '../api/errors'
import { seedOnboardedMe } from './db'

/**
 * The mock API only earns its keep if it refuses what the real backend refuses.
 * These pin the rules that have already drifted once.
 */
describe('mock API matches the contract', () => {
  it('rejects a phone the contract pattern forbids, on onboarding', async () => {
    const error = (await api
      .post('/users/me/onboarding', {
        name: 'Dvir Levi',
        phone: '+1 (555) 010-9999',
        date_of_birth: '1996-02-11',
        accepted_terms: true,
      })
      .catch((caught: unknown) => caught)) as ApiError

    expect(error.code).toBe('VALIDATION_ERROR')
    expect(error.fieldError('phone')).toBeDefined()
  })

  it('rejects the same phone on PATCH /users/me', async () => {
    seedOnboardedMe()

    const error = (await api
      .patch('/users/me', { phone: '+1 (555) 010-9999' })
      .catch((caught: unknown) => caught)) as ApiError

    expect(error.status).toBe(422)
    expect(error.fieldError('phone')).toBeDefined()
  })

  it('accepts a well-formed phone and still lets null clear it', async () => {
    seedOnboardedMe()

    await expect(api.patch('/users/me', { phone: '+972 50-123-4567' })).resolves.toMatchObject({
      phone: '+972 50-123-4567',
    })
    await expect(api.patch('/users/me', { phone: null })).resolves.toMatchObject({ phone: null })
  })

  it('requires a real boolean for accepted_terms', async () => {
    const error = (await api
      .post('/users/me/onboarding', {
        name: 'Dvir Levi',
        date_of_birth: '1996-02-11',
        accepted_terms: 'yes',
      })
      .catch((caught: unknown) => caught)) as ApiError

    expect(error.code).toBe('TERMS_NOT_ACCEPTED')
  })
})
