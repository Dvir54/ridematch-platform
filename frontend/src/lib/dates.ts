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

/** Just the clock time, for a row that already says which day it is. */
export function formatTime(iso: string, locale?: string): string {
  return new Date(iso).toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' })
}

/** "Thu 8 Oct" — the day of a departure, without the time. */
export function formatDay(iso: string, locale?: string): string {
  return new Date(iso).toLocaleDateString(locale, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  })
}

/**
 * `<input type="datetime-local">` speaks the user's own zone with no offset, so
 * both directions convert explicitly. The wire format is UTC with `Z`, which
 * the server accepts alongside any other offset (CONTRACT §2).
 */
export function dateTimeLocalToIso(local: string): string | null {
  if (!local) return null
  const parsed = new Date(local)
  return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString()
}

export function isoToDateTimeLocal(iso: string): string {
  const date = new Date(iso)
  const offsetMs = date.getTimezoneOffset() * 60_000
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16)
}

/** The earliest departure the Create Ride form offers: the next whole minute. */
export function soonestDepartureInput(now: Date = new Date()): string {
  return isoToDateTimeLocal(new Date(now.getTime() + 60_000).toISOString())
}

const HOUR_MS = 3_600_000

/** A driver may start from two hours out (CONTRACT §3; 409 TOO_EARLY_TO_START). */
export function canStartYet(departureIso: string, now: Date = new Date()): boolean {
  return now.getTime() >= new Date(departureIso).getTime() - 2 * HOUR_MS
}

/**
 * An approved passenger may cancel until an hour before departure (D15).
 * The UI uses this to explain the lock; the backend still enforces it.
 */
export function canCancelApprovedYet(departureIso: string, now: Date = new Date()): boolean {
  return now.getTime() < new Date(departureIso).getTime() - HOUR_MS
}

export function isPast(iso: string, now: Date = new Date()): boolean {
  return new Date(iso).getTime() <= now.getTime()
}
