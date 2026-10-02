export interface VehicleFields {
  make: string
  model: string
  color: string
  plate: string
}

export type VehicleErrors = Partial<Record<keyof VehicleFields, string>>

/** The one vehicle validation, shared by onboarding and the profile editor. */
export function validateVehicle(fields: VehicleFields): VehicleErrors {
  const errors: VehicleErrors = {}
  if (!fields.make.trim()) errors.make = 'Required.'
  if (!fields.model.trim()) errors.model = 'Required.'
  if (!fields.color.trim()) errors.color = 'Required.'
  if (fields.plate.trim().length < 2) errors.plate = 'Enter the plate as it appears on the car.'
  return errors
}
