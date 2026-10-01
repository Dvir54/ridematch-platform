/**
 * Mapbox hands back a full postal address ("Rothschild Boulevard 1, Tel
 * Aviv-Yafo, Israel"). A ride row only has one line for it, and the country
 * never tells the reader anything, so lists show the street and the town and the
 * detail screen shows the whole thing.
 */
export function shortAddress(address: string): string {
  const parts = address.split(',').map((part) => part.trim()).filter(Boolean)
  if (parts.length <= 2) return parts.join(', ')
  return parts.slice(0, 2).join(', ')
}
