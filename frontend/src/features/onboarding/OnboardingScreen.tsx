import { useState } from 'react'
import type { FormEvent } from 'react'
import { useUser } from '@clerk/clerk-react'
import { Navigate, useNavigate } from 'react-router-dom'
import { useCompleteOnboarding, useSession } from '../../api/hooks/users'
import { isApiError, messageFor } from '../../api/errors'
import type { Gender, OnboardingRequest } from '../../api/types'
import { Button } from '../../components/Button'
import { CheckboxField, SelectField, TextField } from '../../components/Field'
import { ErrorNotice, FullScreenLoader } from '../../components/states'
import { Wordmark } from '../../components/Wordmark'
import { isAdult, todayAsDateInput } from '../../lib/dates'

const GENDERS: { value: Gender; label: string }[] = [
  { value: 'female', label: 'Female' },
  { value: 'male', label: 'Male' },
  { value: 'other', label: 'Other' },
  { value: 'prefer_not_to_say', label: 'Prefer not to say' },
]

const PHONE_PATTERN = /^\+?[0-9 -]{7,20}$/

interface FormState {
  name: string
  phone: string
  dateOfBirth: string
  gender: string
  addVehicle: boolean
  make: string
  model: string
  color: string
  plate: string
  acceptedTerms: boolean
}

type Errors = Partial<Record<keyof FormState, string>>

function validate(form: FormState): Errors {
  const errors: Errors = {}

  if (!form.name.trim()) errors.name = 'Tell drivers what to call you.'
  if (form.phone.trim() && !PHONE_PATTERN.test(form.phone.trim())) {
    errors.phone = 'Use digits, spaces and dashes, 7 to 20 characters.'
  }

  if (!form.dateOfBirth) {
    errors.dateOfBirth = 'Enter your date of birth.'
  } else if (!isAdult(form.dateOfBirth)) {
    errors.dateOfBirth = 'You must be 18 or older to use RideMatch.'
  }

  if (form.addVehicle) {
    if (!form.make.trim()) errors.make = 'Required.'
    if (!form.model.trim()) errors.model = 'Required.'
    if (!form.color.trim()) errors.color = 'Required.'
    if (form.plate.trim().length < 2) errors.plate = 'Enter the plate as it appears on the car.'
  }

  if (!form.acceptedTerms) errors.acceptedTerms = 'Accept the terms to continue.'

  return errors
}

export function OnboardingScreen() {
  const navigate = useNavigate()
  const { user } = useUser()
  const session = useSession()
  const onboard = useCompleteOnboarding()

  const [form, setForm] = useState<FormState>({
    name: '',
    phone: '',
    dateOfBirth: '',
    gender: '',
    addVehicle: false,
    make: '',
    model: '',
    color: '',
    plate: '',
    acceptedTerms: false,
  })
  const [errors, setErrors] = useState<Errors>({})
  const [nameTouched, setNameTouched] = useState(false)

  // Clerk already collected a name at sign-up; offer it instead of asking twice.
  const name = nameTouched ? form.name : form.name || (user?.fullName ?? '')

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((previous) => ({ ...previous, [key]: value }))
    setErrors((previous) => ({ ...previous, [key]: undefined }))
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const candidate = { ...form, name }
    const found = validate(candidate)
    setErrors(found)
    if (Object.keys(found).length > 0) return

    const body: OnboardingRequest = {
      name: candidate.name.trim(),
      phone: candidate.phone.trim() || null,
      date_of_birth: candidate.dateOfBirth,
      gender: candidate.gender ? (candidate.gender as Gender) : null,
      vehicle: candidate.addVehicle
        ? {
            make: candidate.make.trim(),
            model: candidate.model.trim(),
            color: candidate.color.trim(),
            plate: candidate.plate.trim().toUpperCase(),
          }
        : null,
      accepted_terms: true,
    }

    try {
      await onboard.mutateAsync(body)
      navigate('/app', { replace: true })
    } catch (error) {
      if (!isApiError(error)) return
      if (error.is('ALREADY_ONBOARDED')) {
        await session.refetch()
        navigate('/app', { replace: true })
        return
      }
      setErrors({
        name: error.fieldError('name'),
        phone: error.fieldError('phone'),
        dateOfBirth: error.is('UNDERAGE')
          ? 'You must be 18 or older to use RideMatch.'
          : error.fieldError('date_of_birth'),
        acceptedTerms: error.is('TERMS_NOT_ACCEPTED')
          ? 'Accept the terms to continue.'
          : error.fieldError('accepted_terms'),
      })
    }
  }

  if (session.isPending) return <FullScreenLoader label="Loading your profile" />
  if (session.data?.status === 'ready') return <Navigate to="/app" replace />

  const failure = onboard.isError && isApiError(onboard.error) ? onboard.error : null
  const showBanner =
    failure !== null && !failure.is('UNDERAGE', 'TERMS_NOT_ACCEPTED', 'VALIDATION_ERROR')

  return (
    <div className="mx-auto min-h-dvh w-full max-w-[34rem] px-5 py-8">
      <Wordmark className="text-lg" />

      <h1 className="mt-10 text-2xl">Set up your profile</h1>
      <p className="mt-3 max-w-[48ch] text-ink-70">
        Drivers and passengers see your name and ratings before they agree to share a car.
        {user?.primaryEmailAddress
          ? ` Signed in as ${user.primaryEmailAddress.emailAddress}.`
          : ''}
      </p>

      <form className="mt-8 flex flex-col gap-6" onSubmit={(event) => void handleSubmit(event)}>
        {showBanner ? <ErrorNotice>{messageFor(failure)}</ErrorNotice> : null}

        <TextField
          label="Name"
          autoComplete="name"
          value={name}
          error={errors.name}
          onChange={(event) => {
            setNameTouched(true)
            set('name', event.target.value)
          }}
        />

        <TextField
          label="Phone"
          type="tel"
          optional
          autoComplete="tel"
          hint="Shared with the other side once a seat is agreed."
          value={form.phone}
          error={errors.phone}
          onChange={(event) => set('phone', event.target.value)}
        />

        <TextField
          label="Date of birth"
          type="date"
          max={todayAsDateInput()}
          autoComplete="bday"
          hint="RideMatch is for people aged 18 and over."
          value={form.dateOfBirth}
          error={errors.dateOfBirth}
          onChange={(event) => set('dateOfBirth', event.target.value)}
        />

        <SelectField
          label="Gender"
          optional
          hint="Only used for rides a driver limits to passengers of their own gender."
          value={form.gender}
          error={errors.gender}
          onChange={(event) => set('gender', event.target.value)}
        >
          <option value="">Not specified</option>
          {GENDERS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </SelectField>

        <fieldset className="rounded-card border border-hairline bg-surface p-5">
          <legend className="px-1 text-sm font-semibold">Your car</legend>
          <CheckboxField
            label="I plan to offer rides, so add my car now"
            checked={form.addVehicle}
            onChange={(event) => set('addVehicle', event.target.checked)}
          />
          <p className="mt-2 ml-7 text-sm text-ink-70">
            You can add it later. A car is required before you can offer a ride.
          </p>

          {form.addVehicle ? (
            <div className="mt-5 grid gap-4 sm:grid-cols-2">
              <TextField
                label="Make"
                placeholder="Toyota"
                value={form.make}
                error={errors.make}
                onChange={(event) => set('make', event.target.value)}
              />
              <TextField
                label="Model"
                placeholder="Corolla"
                value={form.model}
                error={errors.model}
                onChange={(event) => set('model', event.target.value)}
              />
              <TextField
                label="Colour"
                placeholder="White"
                value={form.color}
                error={errors.color}
                onChange={(event) => set('color', event.target.value)}
              />
              <TextField
                label="Licence plate"
                placeholder="12-345-67"
                hint="Only passengers you approve can see this."
                value={form.plate}
                error={errors.plate}
                onChange={(event) => set('plate', event.target.value)}
              />
            </div>
          ) : null}
        </fieldset>

        <CheckboxField
          label="I accept the RideMatch terms of service and privacy policy."
          checked={form.acceptedTerms}
          error={errors.acceptedTerms}
          onChange={(event) => set('acceptedTerms', event.target.checked)}
        />

        <Button type="submit" full disabled={onboard.isPending}>
          {onboard.isPending ? 'Creating your profile' : 'Create profile'}
        </Button>
      </form>
    </div>
  )
}
