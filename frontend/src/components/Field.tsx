import { useId } from 'react'
import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from 'react'

const control =
  'w-full rounded-card border bg-surface px-3 py-2.5 text-base placeholder:text-ink-45'

function describedBy(id: string, hint?: string, error?: string): string | undefined {
  const ids = [hint ? `${id}-hint` : null, error ? `${id}-error` : null].filter(Boolean)
  return ids.length ? ids.join(' ') : undefined
}

function Labelled({
  id,
  label,
  hint,
  error,
  optional,
  children,
}: {
  id: string
  label: string
  hint?: string
  error?: string
  optional?: boolean
  children: ReactNode
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-semibold">
        {label}
        {optional ? <span className="ml-2 font-normal text-ink-45">optional</span> : null}
      </label>
      {hint ? (
        <p id={`${id}-hint`} className="text-sm text-ink-70">
          {hint}
        </p>
      ) : null}
      {children}
      {error ? (
        <p id={`${id}-error`} className="text-sm font-medium text-alert">
          {error}
        </p>
      ) : null}
    </div>
  )
}

export interface TextFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string
  hint?: string
  error?: string
  optional?: boolean
}

export function TextField({ label, hint, error, optional, id, ...props }: TextFieldProps) {
  const generated = useId()
  const fieldId = id ?? generated
  return (
    <Labelled id={fieldId} label={label} hint={hint} error={error} optional={optional}>
      <input
        {...props}
        id={fieldId}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(fieldId, hint, error)}
        className={`${control} ${error ? 'border-alert' : 'border-hairline'}`}
      />
    </Labelled>
  )
}

export interface SelectFieldProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label: string
  hint?: string
  error?: string
  optional?: boolean
}

export function SelectField({
  label,
  hint,
  error,
  optional,
  id,
  children,
  ...props
}: SelectFieldProps) {
  const generated = useId()
  const fieldId = id ?? generated
  return (
    <Labelled id={fieldId} label={label} hint={hint} error={error} optional={optional}>
      <select
        {...props}
        id={fieldId}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(fieldId, hint, error)}
        className={`${control} ${error ? 'border-alert' : 'border-hairline'}`}
      >
        {children}
      </select>
    </Labelled>
  )
}

export interface CheckboxFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: ReactNode
  error?: string
}

export function CheckboxField({ label, error, id, ...props }: CheckboxFieldProps) {
  const generated = useId()
  const fieldId = id ?? generated
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-start gap-3">
        <input
          {...props}
          type="checkbox"
          id={fieldId}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${fieldId}-error` : undefined}
          className="mt-1 size-4.5 shrink-0 accent-[var(--color-ink)]"
        />
        <label htmlFor={fieldId} className="text-sm leading-snug">
          {label}
        </label>
      </div>
      {error ? (
        <p id={`${fieldId}-error`} className="text-sm font-medium text-alert">
          {error}
        </p>
      ) : null}
    </div>
  )
}
