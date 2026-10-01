/** Whole years between a `YYYY-MM-DD` birth date and a reference day. */
export function yearsOld(dateOfBirth: string, today: Date = new Date()): number {
  const [year, month, day] = dateOfBirth.split('-').map(Number)
  if (!year || !month || !day) return Number.NaN

  let age = today.getFullYear() - year
  const hadBirthday =
    today.getMonth() + 1 > month || (today.getMonth() + 1 === month && today.getDate() >= day)
  if (!hadBirthday) age -= 1
  return age
}

/** RideMatch is 18+ (CONTRACT §4). Checked here and again by the backend. */
export function isAdult(dateOfBirth: string, today: Date = new Date()): boolean {
  const age = yearsOld(dateOfBirth, today)
  return Number.isFinite(age) && age >= 18
}

/** Today as `YYYY-MM-DD` in the user's own zone — the max for a birth-date input. */
export function todayAsDateInput(today: Date = new Date()): string {
  const offsetMs = today.getTimezoneOffset() * 60_000
  return new Date(today.getTime() - offsetMs).toISOString().slice(0, 10)
}

/** Times are stored UTC and always shown in the reader's zone (role brief). */
export function formatDateTime(iso: string, locale?: string): string {
  return new Date(iso).toLocaleString(locale, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}
