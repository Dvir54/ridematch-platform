import { SignIn, SignUp } from '@clerk/clerk-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Wordmark } from '../../components/Wordmark'
import { clerkAppearance } from './clerkAppearance'

function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col items-center gap-8 px-5 py-8">
      <Link to="/" className="self-start text-lg">
        <Wordmark />
      </Link>
      {children}
    </div>
  )
}

export function SignInScreen() {
  return (
    <AuthLayout>
      <SignIn
        routing="path"
        path="/sign-in"
        signUpUrl="/sign-up"
        forceRedirectUrl="/app"
        appearance={clerkAppearance}
      />
    </AuthLayout>
  )
}

export function SignUpScreen() {
  return (
    <AuthLayout>
      <SignUp
        routing="path"
        path="/sign-up"
        signInUrl="/sign-in"
        forceRedirectUrl="/app"
        appearance={clerkAppearance}
      />
    </AuthLayout>
  )
}
