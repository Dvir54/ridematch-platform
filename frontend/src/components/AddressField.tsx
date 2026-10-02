import { useEffect, useId, useRef, useState } from 'react'
import { env } from '../env'
import type { AddressSuggestion, AddressValue } from '../lib/mapbox'
import { searchAddresses } from '../lib/mapbox'

const DEBOUNCE_MS = 250
const MIN_QUERY = 3

export interface AddressFieldProps {
  label: string
  /** The chosen place, or null while the text does not yet name one. */
  value: AddressValue | null
  onChange: (value: AddressValue | null) => void
  hint?: string
  error?: string
  placeholder?: string
}

const control =
  'w-full rounded-card border bg-surface px-3 py-2.5 text-base placeholder:text-ink-45'

/**
 * A place picker, not a text box: coordinates are as much part of the answer as
 * the address, so the field only counts as filled once a suggestion is chosen
 * (scope G5a). Typing after a choice clears it, which is what keeps a ride from
 * being posted with a hand-edited address pinned to the wrong coordinates.
 *
 * Built as an ARIA combobox rather than with Mapbox's own widget so it matches
 * every other field on the form and can be driven from a test.
 */
export function AddressField({
  label,
  value,
  onChange,
  hint,
  error,
  placeholder,
}: AddressFieldProps) {
  const id = useId()
  const listId = `${id}-list`
  const [text, setText] = useState(value?.address ?? '')
  const [suggestions, setSuggestions] = useState<AddressSuggestion[]>([])
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const [lookupFailed, setLookupFailed] = useState(false)

  // The lookup is debounced from the change handler rather than from an effect
  // on `text`: picking a suggestion also sets the text, and an effect would
  // immediately search for the thing that was just chosen.
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined)
  const inFlight = useRef<AbortController>(undefined)

  useEffect(
    () => () => {
      clearTimeout(timer.current)
      inFlight.current?.abort()
    },
    [],
  )

  function cancelLookup() {
    clearTimeout(timer.current)
    inFlight.current?.abort()
  }

  function closeList() {
    setSuggestions([])
    setOpen(false)
    setActive(-1)
  }

  function onType(next: string) {
    setText(next)
    // The old coordinates no longer describe what is in the box.
    if (value) onChange(null)

    cancelLookup()
    const query = next.trim()
    if (!env.mapboxToken || query.length < MIN_QUERY) {
      closeList()
      return
    }

    const controller = new AbortController()
    inFlight.current = controller
    timer.current = setTimeout(() => {
      searchAddresses(query, { signal: controller.signal })
        .then((found) => {
          setSuggestions(found)
          setActive(-1)
          setOpen(found.length > 0)
          setLookupFailed(false)
        })
        .catch((cause: unknown) => {
          if (cause instanceof DOMException && cause.name === 'AbortError') return
          closeList()
          setLookupFailed(true)
        })
    }, DEBOUNCE_MS)
  }

  function choose(suggestion: AddressSuggestion) {
    cancelLookup()
    setText(suggestion.address)
    closeList()
    onChange({ address: suggestion.address, lat: suggestion.lat, lng: suggestion.lng })
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Escape') {
      setOpen(false)
      return
    }
    if (!open || suggestions.length === 0) return

    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActive((current) => (current + 1) % suggestions.length)
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActive((current) => (current <= 0 ? suggestions.length - 1 : current - 1))
    } else if (event.key === 'Enter') {
      // Enter on a highlighted option picks it instead of submitting the form.
      const picked = suggestions[active]
      if (picked) {
        event.preventDefault()
        choose(picked)
      }
    }
  }

  const noToken = !env.mapboxToken
  const problem = error
    ? error
    : noToken
      ? 'Address search needs VITE_MAPBOX_TOKEN in the .env file at the repo root.'
      : lookupFailed
        ? 'Address search is unavailable right now. Try again in a moment.'
        : undefined

  const describedBy =
    [hint ? `${id}-hint` : null, problem ? `${id}-error` : null].filter(Boolean).join(' ') ||
    undefined

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-semibold">
        {label}
      </label>
      {hint ? (
        <p id={`${id}-hint`} className="text-sm text-ink-70">
          {hint}
        </p>
      ) : null}

      <div className="relative">
        <input
          id={id}
          type="text"
          role="combobox"
          autoComplete="off"
          disabled={noToken}
          placeholder={placeholder}
          value={text}
          aria-expanded={open}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={active >= 0 ? `${id}-option-${active}` : undefined}
          aria-invalid={problem ? true : undefined}
          aria-describedby={describedBy}
          onChange={(event) => onType(event.target.value)}
          onKeyDown={onKeyDown}
          onBlur={() => setOpen(false)}
          className={`${control} ${problem ? 'border-alert' : 'border-hairline'}`}
        />

        <ul
          id={listId}
          role="listbox"
          aria-label={`${label} suggestions`}
          hidden={!open}
          className="absolute inset-x-0 top-full z-10 mt-1 overflow-hidden rounded-card border border-hairline bg-surface shadow-lg"
        >
          {suggestions.map((suggestion, index) => (
            <li
              key={suggestion.id}
              id={`${id}-option-${index}`}
              role="option"
              aria-selected={index === active}
              // mousedown, not click: blur would close the list first.
              onMouseDown={(event) => {
                event.preventDefault()
                choose(suggestion)
              }}
              onMouseEnter={() => setActive(index)}
              className={`cursor-pointer px-3 py-2.5 text-sm ${index === active ? 'bg-paper' : ''}`}
            >
              <span className="block font-medium">{suggestion.address}</span>
              {suggestion.context ? (
                <span className="block text-ink-45">{suggestion.context}</span>
              ) : null}
            </li>
          ))}
        </ul>
      </div>

      {problem ? (
        <p id={`${id}-error`} className="text-sm font-medium text-alert">
          {problem}
        </p>
      ) : null}
    </div>
  )
}
