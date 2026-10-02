const LIMIT = 20

export { LIMIT }

/** "1–20 of 134" with Prev/Next, driven by `limit`/`offset` and `X-Total-Count`. */
export function Pager({
  offset,
  total,
  onChange,
}: {
  offset: number
  total: number
  onChange: (offset: number) => void
}) {
  if (total === 0) return null

  const from = offset + 1
  const to = Math.min(offset + LIMIT, total)

  return (
    <div className="mt-4 flex items-center justify-between gap-3 text-sm">
      <p className="tnum text-ink-70">
        {from}–{to} of {total}
      </p>
      <div className="flex gap-2">
        <button
          type="button"
          disabled={offset === 0}
          onClick={() => onChange(Math.max(0, offset - LIMIT))}
          className="rounded-full border border-hairline px-3 py-1 font-semibold text-ink-70 hover:border-ink hover:text-ink disabled:cursor-not-allowed disabled:opacity-45"
        >
          Previous
        </button>
        <button
          type="button"
          disabled={to >= total}
          onClick={() => onChange(offset + LIMIT)}
          className="rounded-full border border-hairline px-3 py-1 font-semibold text-ink-70 hover:border-ink hover:text-ink disabled:cursor-not-allowed disabled:opacity-45"
        >
          Next
        </button>
      </div>
    </div>
  )
}
