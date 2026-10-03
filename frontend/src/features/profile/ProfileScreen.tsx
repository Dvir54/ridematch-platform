import { useClerk } from '@clerk/clerk-react'
import { messageFor } from '../../api/errors'
import { useMyStats } from '../../api/hooks/users'
import { useCurrentUser } from '../../auth/currentUserContext'
import { Button, ButtonLink } from '../../components/Button'
import { StatsGrid } from '../../components/StatsGrid'
import { TabHeader } from '../../components/TabHeader'
import { InlineLoader, LoadFailure } from '../../components/states'
import { formatRating } from '../../lib/rating'
import { paths } from '../../routes'
import { LegalLinks, PrivacyContact } from '../legal/LegalScreen'
import { VehicleEditor } from './VehicleEditor'

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-hairline py-3 last:border-b-0">
      <dt className="text-sm text-ink-70">{label}</dt>
      <dd className="tnum text-right font-medium">{value}</dd>
    </div>
  )
}

/** The full trip record behind the quick counters on each Home screen. */
function TripStats() {
  const stats = useMyStats()

  if (stats.isPending) return <InlineLoader label="Loading your trip history" />
  if (stats.isError) {
    return (
      <LoadFailure
        title="Your trip history did not load"
        message={messageFor(stats.error)}
        onRetry={() => void stats.refetch()}
      />
    )
  }

  const { as_driver, as_passenger } = stats.data

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h3 className="mb-2 text-sm font-semibold">As a driver</h3>
        <StatsGrid
          items={[
            { label: 'Rides offered', value: as_driver.rides_offered },
            { label: 'Completed', value: as_driver.rides_completed },
            { label: 'Passengers carried', value: as_driver.passengers_carried },
          ]}
        />
      </div>
      <div>
        <h3 className="mb-2 text-sm font-semibold">As a passenger</h3>
        <StatsGrid
          items={[
            { label: 'Trips requested', value: as_passenger.trips_requested },
            { label: 'Completed', value: as_passenger.trips_completed },
            { label: 'Upcoming', value: as_passenger.upcoming_trips },
          ]}
        />
      </div>
    </div>
  )
}

export function ProfileScreen() {
  const user = useCurrentUser()
  const { openUserProfile, signOut } = useClerk()

  const memberSince = new Date(user.created_at).toLocaleDateString(undefined, {
    month: 'long',
    year: 'numeric',
  })

  return (
    <>
      <TabHeader title={user.name} lead={user.email} />

      <section className="rounded-card border border-hairline bg-surface px-5 py-2">
        <h2 className="sr-only">Your account</h2>
        <dl>
          <Row label="Member since" value={memberSince} />
          <Row
            label="As a driver"
            value={formatRating(user.driver_rating, user.driver_rating_count)}
          />
          <Row
            label="As a passenger"
            value={formatRating(user.passenger_rating, user.passenger_rating_count)}
          />
        </dl>
      </section>

      <section className="mt-5">
        <h2 className="mb-3 text-lg">Your trips</h2>
        <TripStats />
      </section>

      <section className="mt-5 rounded-card border border-hairline bg-surface px-5 py-4">
        <h2 className="text-sm font-semibold">Your car</h2>
        {user.vehicle ? (
          <dl className="mt-2">
            <Row
              label="Car"
              value={`${user.vehicle.color} ${user.vehicle.make} ${user.vehicle.model}`}
            />
            <Row label="Plate" value={user.vehicle.plate} />
          </dl>
        ) : (
          <p className="mt-2 text-sm text-ink-70">
            No car added. You need one on your profile before you can offer a ride.
          </p>
        )}
        <div className="mt-4">
          <VehicleEditor vehicle={user.vehicle ?? null} />
        </div>
      </section>

      {user.is_admin ? (
        <div className="mt-5">
          <ButtonLink to={paths.admin} variant="secondary" full>
            Admin panel
          </ButtonLink>
        </div>
      ) : null}

      <div className="mt-8 flex flex-col gap-3">
        <Button variant="secondary" full onClick={() => openUserProfile()}>
          Manage account
        </Button>
        <Button variant="quiet" full onClick={() => void signOut()}>
          Sign out
        </Button>
      </div>

      <footer className="mt-8 border-t border-hairline pt-4 text-sm text-ink-70">
        <LegalLinks />
        <p className="mt-2">
          Privacy questions and deletion requests: <PrivacyContact />
        </p>
      </footer>
    </>
  )
}
