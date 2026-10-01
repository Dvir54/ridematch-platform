import type { ButtonHTMLAttributes } from 'react'
import { Link } from 'react-router-dom'

type Variant = 'primary' | 'secondary' | 'quiet'

const base =
  'inline-flex items-center justify-center gap-2 rounded-card px-5 py-3 text-base font-semibold ' +
  'transition-colors disabled:cursor-not-allowed disabled:opacity-45'

const variants: Record<Variant, string> = {
  // Amber is the loudest thing in the app. One per screen, on the action the
  // screen exists for.
  primary: 'bg-signal text-ink hover:bg-signal-deep hover:text-surface',
  secondary: 'border border-ink text-ink hover:bg-ink hover:text-surface',
  quiet: 'text-ink-70 underline decoration-ink/30 underline-offset-4 hover:text-ink',
}

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  full?: boolean
}

export function Button({ variant = 'primary', full, className = '', ...props }: ButtonProps) {
  return (
    <button
      {...props}
      className={`${base} ${variants[variant]} ${full ? 'w-full' : ''} ${className}`}
    />
  )
}

export interface ButtonLinkProps {
  to: string
  variant?: Variant
  full?: boolean
  children: React.ReactNode
}

export function ButtonLink({ to, variant = 'primary', full, children }: ButtonLinkProps) {
  return (
    <Link to={to} className={`${base} ${variants[variant]} ${full ? 'w-full' : ''}`}>
      {children}
    </Link>
  )
}
