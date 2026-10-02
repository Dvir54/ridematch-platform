/** The one-line summary for a cached average + count, shared by every screen that shows one. */
export function formatRating(score: number | null | undefined, count: number): string {
  if (score === null || score === undefined || count === 0) return 'Not rated yet'
  return `${score.toFixed(1)} from ${count} ${count === 1 ? 'rating' : 'ratings'}`
}
