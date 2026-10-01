/** The product name set as a journey: two syllables, one arrow between them. */
export function Wordmark({ className = '' }: { className?: string }) {
  return (
    <span className={`inline-flex items-baseline gap-1 font-semibold tracking-tight ${className}`}>
      Ride
      <span
        aria-hidden="true"
        className="relative bottom-[0.18em] size-0 border-y-[0.26em] border-l-[0.4em] border-y-transparent border-l-signal-deep"
      />
      Match
    </span>
  )
}
