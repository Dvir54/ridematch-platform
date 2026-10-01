import { useClerk } from '@clerk/clerk-react'
import { useCurrentUser } from '../../auth/currentUserContext'
import { Button } from '../../components/Button'
import { TabHeader } from '../../components/TabHeader'

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-hairline py-3 last:border-b-0">
      <dt className="text-sm text-ink-70">{label}</dt>
      <dd className="tnum text-right font-medium">{value}</dd>
    </div>
  )
}

function rating(score: number | null | undefined, count: number): string {
  if (score === null || score === undefined || count === 0) return 'Not rated yet'
  return `${score.toFixed(1)} from ${count} ${count === 1 ? 'rating' : 'ratings'}`
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
          <Row label="As a driver" value={rating(user.driver_rating, user.driver_rating_count)} />
          <Row
            label="As a passenger"
            value={rating(user.passenger_rating, user.passenger_rating_count)}
          />
          <Row label="Phone" value={user.phone ?? 'Not added'} />
        </dl>
      </section>

      <section className="mt-5 rounded-card border border-hairline bg-surface px-5 py-2">
        <h2 className="sr-only">Your car</h2>
        {user.vehicle ? (
          <dl>
            <Row
              label="Car"
              value={`${user.vehicle.color} ${user.vehicle.make} ${user.vehicle.model}`}
            />
            <Row label="Plate" value={user.vehicle.plate} />
          </dl>
        ) : (
          <p className="py-3 text-sm text-ink-70">
            No car added. You need one on your profile before you can offer a ride.
          </p>
        )}
      </section>

      <div className="mt-8 flex flex-col gap-3">
        <Button variant="secondary" full onClick={() => openUserProfile()}>
          Manage account
        </Button>
        <Button variant="quiet" full onClick={() => void signOut()}>
          Sign out
        </Button>
      </div>
    </>
  )
}
