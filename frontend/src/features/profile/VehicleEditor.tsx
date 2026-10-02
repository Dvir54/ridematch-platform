import { useState } from 'react'
import type { FormEvent } from 'react'
import { messageFor } from '../../api/errors'
import { collectFieldErrors } from '../../api/fieldErrors'
import { useUpdateMe } from '../../api/hooks/users'
import type { Vehicle } from '../../api/types'
import { Button } from '../../components/Button'
import { ConfirmAction } from '../../components/ConfirmAction'
import { TextField } from '../../components/Field'
import { ErrorNotice } from '../../components/states'
import type { VehicleFields } from '../../lib/vehicle'
import { validateVehicle } from '../../lib/vehicle'

const FIELD_OWNERS: Record<string, keyof VehicleFields> = {
  'vehicle.make': 'make',
  'vehicle.model': 'model',
  'vehicle.color': 'color',
  'vehicle.plate': 'plate',
}

function toFields(vehicle: Vehicle | null): VehicleFields {
  return vehicle
    ? { make: vehicle.make, model: vehicle.model, color: vehicle.color, plate: vehicle.plate }
    : { make: '', model: '', color: '', plate: '' }
}

/**
 * Add/edit car on the profile, using the same fields and validation as
 * onboarding (`lib/vehicle.ts`), via `PATCH /users/me`. A full replace, same
 * as the contract's `UserUpdate.vehicle` (no partial vehicle updates).
 */
export function VehicleEditor({ vehicle }: { vehicle: Vehicle | null }) {
  const [editing, setEditing] = useState(false)
  const [fields, setFields] = useState<VehicleFields>(() => toFields(vehicle))
  const [errors, setErrors] = useState<Partial<Record<keyof VehicleFields, string>>>({})
  const update = useUpdateMe()

  function set<K extends keyof VehicleFields>(key: K, value: VehicleFields[K]) {
    setFields((current) => ({ ...current, [key]: value }))
  }

  function startEditing() {
    setFields(toFields(vehicle))
    setErrors({})
    update.reset()
    setEditing(true)
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    const found = validateVehicle(fields)
    setErrors(found)
    if (Object.keys(found).length > 0) return

    update.mutate(
      {
        vehicle: {
          make: fields.make.trim(),
          model: fields.model.trim(),
          color: fields.color.trim(),
          plate: fields.plate.trim().toUpperCase(),
        },
      },
      { onSuccess: () => setEditing(false) },
    )
  }

  function onRemove() {
    update.mutate({ vehicle: null })
  }

  const fromServer = collectFieldErrors(update.error, FIELD_OWNERS)
  const shown = { ...fromServer.fields, ...errors }

  if (!editing) {
    return (
      <div className="flex flex-col gap-3">
        {update.error ? <ErrorNotice>{messageFor(update.error)}</ErrorNotice> : null}
        <div className="flex flex-wrap gap-3">
          <Button variant="secondary" onClick={startEditing}>
            {vehicle ? 'Edit car' : 'Add your car'}
          </Button>
          {vehicle ? (
            <ConfirmAction
              label="Remove car"
              question="You will not be able to offer rides until you add a car again. If you have an upcoming ride, this will be refused."
              confirmLabel="Remove it"
              pending={update.isPending}
              onConfirm={onRemove}
            />
          ) : null}
        </div>
      </div>
    )
  }

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
      {update.error ? (
        <ErrorNotice>
          {messageFor(update.error)}
          {fromServer.rest.map((message) => (
            <span key={message} className="mt-1 block font-normal">
              {message}
            </span>
          ))}
        </ErrorNotice>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2">
        <TextField
          label="Make"
          placeholder="Toyota"
          value={fields.make}
          error={shown.make}
          onChange={(event) => set('make', event.target.value)}
        />
        <TextField
          label="Model"
          placeholder="Corolla"
          value={fields.model}
          error={shown.model}
          onChange={(event) => set('model', event.target.value)}
        />
        <TextField
          label="Colour"
          placeholder="White"
          value={fields.color}
          error={shown.color}
          onChange={(event) => set('color', event.target.value)}
        />
        <TextField
          label="Licence plate"
          placeholder="12-345-67"
          hint="Only passengers you approve can see this."
          value={fields.plate}
          error={shown.plate}
          onChange={(event) => set('plate', event.target.value)}
        />
      </div>

      <div className="flex flex-wrap gap-3">
        <Button type="submit" disabled={update.isPending}>
          {update.isPending ? 'Saving…' : 'Save car'}
        </Button>
        <Button type="button" variant="quiet" disabled={update.isPending} onClick={() => setEditing(false)}>
          Discard
        </Button>
      </div>
    </form>
  )
}
