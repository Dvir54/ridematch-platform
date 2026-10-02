/** Capped exponential backoff for reconnect attempts: 1s, 2s, 4s, …, up to 30s. */
export function backoffDelay(attempt: number, baseMs = 1_000, maxMs = 30_000): number {
  return Math.min(baseMs * 2 ** attempt, maxMs)
}
