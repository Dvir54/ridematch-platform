import { useId, useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { messageFor } from '../../api/errors'
import { useCreateRating } from '../../api/hooks/ratings'
import { useRide } from '../../api/hooks/rides'
import { useUserPublic } from '../../api/hooks/users'
import { ButtonLink, Button } from '../../components/Button'
import { TextareaField } from '../../components/Field'
import { TabHeader } from '../../components/TabHeader'
import { ErrorNotice, InlineLoader, LoadFailure, MessageScreen } from '../../components/states'
import { useCurrentUser } from '../../auth/currentUserContext'
import { homePathFor } from '../../routes'

const TAGS = ['on_time', 'friendly', 'clean_car', 'safe_driving', 'good_route'] as const

function useRouteRating() {
  const { rideId, userId } = useParams<{ rideId: string; userId: string }>()
  const ride = Number(rideId)
  const user = Number(userId)
  const valid = Number.isInteger(ride) && ride > 0 && Number.isInteger(user) && user > 0
  return valid ? { rideId: ride, userId: user } : { rideId: undefined, userId: undefined }
}

function ScorePicker({ value, onChange }: { value: number | null; onChange: (score: number) => void }) {
  const name = useId()
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="text-sm font-semibold">How was it?</legend>
      <div className="flex gap-2">
        {[1, 2, 3, 4, 5].map((score) => (
          <label
            key={score}
            className={`flex size-11 cursor-pointer items-center justify-center rounded-card border text-base font-semibold ${
              value === score ? 'border-ink bg-ink text-surface' : 'border-hairline'
            }`}
          >
            <input
              type="radio"
              name={name}
              value={score}
              checked={value === score}
              onChange={() => onChange(score)}
              className="sr-only"
            />
            {score}
          </label>
        ))}
      </div>
    </fieldset>
  )
}

function TagPicker({ selected, onToggle }: { selected: Set<string>; onToggle: (tag: string) => void }) {
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="text-sm font-semibold">
        What stood out <span className="font-normal text-ink-45">optional</span>
      </legend>
      <div className="flex flex-wrap gap-2">
        {TAGS.map((tag) => (
          <button
            key={tag}
            type="button"
            aria-pressed={selected.has(tag)}
            onClick={() => onToggle(tag)}
            className={`rounded-full border px-3 py-1.5 text-sm font-medium ${
              selected.has(tag) ? 'border-ink bg-ink text-surface' : 'border-hairline text-ink-70'
            }`}
          >
            {tag.replace(/_/g, ' ')}
          </button>
        ))}
      </div>
    </fieldset>
  )
}

export function RateScreen() {
  const me = useCurrentUser()
  const navigate = useNavigate()
  const { rideId, userId } = useRouteRating()
  const ride = useRide(rideId)
  const toUser = useUserPublic(userId)
  const createRating = useCreateRating()

  const [score, setScore] = useState<number | null>(null)
  const [comment, setComment] = useState('')
  const [tags, setTags] = useState<Set<string>>(new Set())
  const [scoreError, setScoreError] = useState(false)

  const home = homePathFor(me.preferences.default_mode ?? 'passenger')

  if (rideId === undefined || userId === undefined) {
    return (
      <MessageScreen
        title="No such rating"
        body="That link is not pointing at a ride and a person to rate."
        action={<ButtonLink to={home}>Back home</ButtonLink>}
      />
    )
  }

  if (ride.isPending || toUser.isPending) return <InlineLoader label="Loading" />

  if (ride.isError) {
    return (
      <LoadFailure
        title="This ride did not load"
        message={messageFor(ride.error)}
        onRetry={() => void ride.refetch()}
      />
    )
  }
  if (toUser.isError) {
    return (
      <LoadFailure
        title="This person did not load"
        message={messageFor(toUser.error)}
        onRetry={() => void toUser.refetch()}
      />
    )
  }

  const role = ride.data.driver.id === userId ? 'driver' : 'passenger'

  function toggleTag(tag: string) {
    setTags((current) => {
      const next = new Set(current)
      if (next.has(tag)) next.delete(tag)
      else next.add(tag)
      return next
    })
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    if (score === null) {
      setScoreError(true)
      return
    }
    createRating.mutate(
      {
        ride_id: rideId!,
        to_user_id: userId!,
        score,
        comment: comment.trim() === '' ? null : comment.trim(),
        tags: [...tags],
      },
      { onSuccess: () => navigate(home) },
    )
  }

  return (
    <>
      <TabHeader title={`Rate ${toUser.data.name}`} lead={`As your ${role} on this ride.`} />

      <form onSubmit={onSubmit} noValidate className="flex flex-col gap-6">
        {createRating.error ? <ErrorNotice>{messageFor(createRating.error)}</ErrorNotice> : null}

        <ScorePicker
          value={score}
          onChange={(value) => {
            setScore(value)
            setScoreError(false)
          }}
        />
        {scoreError ? <ErrorNotice>Pick a score from 1 to 5.</ErrorNotice> : null}

        <TagPicker selected={tags} onToggle={toggleTag} />

        <TextareaField
          label="Anything else"
          optional
          rows={3}
          value={comment}
          onChange={(event) => setComment(event.target.value)}
        />

        <Button type="submit" disabled={createRating.isPending}>
          {createRating.isPending ? 'Sending…' : 'Send rating'}
        </Button>
      </form>
    </>
  )
}
