/**
 * The app's one signature device: a journey drawn as a rail, origin above
 * destination. Every screen that shows a trip uses it, so a ride always looks
 * like the same object whether it is a search hit, a request or a reminder.
 *
 * The dashes run from the origin square and stop dead at the arrowhead, so the
 * rail always reads as one continuous leg however long the addresses are.
 */
export interface RouteRailProps {
  from: string
  to: string
  /** Optional line under each stop — a time, a distance, a pickup note. */
  fromDetail?: string
  toDetail?: string
  size?: 'display' | 'default'
}

const DASH = 'w-px border-l border-dashed border-ink/40'

export function RouteRail({ from, to, fromDetail, toDetail, size = 'default' }: RouteRailProps) {
  const place = size === 'display' ? 'text-xl leading-tight' : 'text-base leading-snug'

  return (
    <div className="flex flex-col">
      <div className="flex gap-3">
        <span aria-hidden="true" className="flex w-5 flex-col items-center pt-[0.5rem]">
          <span className="size-2.5 shrink-0 bg-ink" />
          <span className={`mt-1 flex-1 ${DASH}`} />
        </span>
        {/* The gap between stops lives here so the rail stretches across it. */}
        <div className="pb-5">
          <p className={`${place} font-semibold`}>{from}</p>
          {fromDetail ? <p className="tnum mt-0.5 text-sm text-ink-70">{fromDetail}</p> : null}
        </div>
      </div>

      <div className="flex gap-3">
        <span aria-hidden="true" className="flex w-5 flex-col items-center">
          <span className={`h-[0.55rem] ${DASH}`} />
          <span className="size-0 border-x-[0.4rem] border-t-[0.6rem] border-x-transparent border-t-signal-deep" />
        </span>
        <div>
          <p className={`${place} font-semibold`}>{to}</p>
          {toDetail ? <p className="tnum mt-0.5 text-sm text-ink-70">{toDetail}</p> : null}
        </div>
      </div>
    </div>
  )
}
