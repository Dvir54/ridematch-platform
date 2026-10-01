import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '../../components/Button'
import { TextField } from '../../components/Field'
import { TabHeader } from '../../components/TabHeader'
import { EmptyState } from '../../components/states'
import { paths } from '../../routes'

/**
 * Matching is Phase 3. Until it lands there is no way to *discover* a ride, so
 * the tab offers the one thing that still works: opening a ride a driver sent
 * you. The form goes when `/search` arrives.
 */
function OpenByNumber() {
  const navigate = useNavigate()
  const [value, setValue] = useState('')
  const rideId = Number(value)
  const valid = Number.isInteger(rideId) && rideId > 0

  return (
    <form
      className="mt-5 flex flex-col gap-3"
      onSubmit={(event) => {
        event.preventDefault()
        if (valid) navigate(paths.passengerRide(rideId))
      }}
    >
      <TextField
        label="Open a ride by its number"
        inputMode="numeric"
        placeholder="101"
        hint="Until search arrives, this is how you reach a ride a driver has shared with you."
        value={value}
        onChange={(event) => setValue(event.target.value)}
      />
      <Button type="submit" variant="secondary" disabled={!valid}>
        Open the ride
      </Button>
    </form>
  )
}

export function SearchScreen() {
  return (
    <>
      <TabHeader title="Search" />
      <EmptyState
        title="Route search is being built"
        body="You will give a pickup point, a destination and a time. RideMatch scores every driver heading the same way and ranks them."
      />
      <OpenByNumber />
    </>
  )
}
