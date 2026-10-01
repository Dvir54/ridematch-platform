import { useNavigate } from 'react-router-dom'
import { useUpdateMe } from '../../api/hooks/users'
import { messageFor } from '../../api/errors'
import type { Mode } from '../../api/types'
import { useCurrentUser } from '../../auth/currentUserContext'
import { SeatIcon, WheelIcon } from '../../components/icons'
import { ErrorNotice } from '../../components/states'
import { Wordmark } from '../../components/Wordmark'
import { homePathFor } from '../../routes'

const CHOICES: {
  mode: Mode
  title: string
  body: string
  Icon: typeof WheelIcon
}[] = [
  {
    mode: 'driver',
    title: 'Offer seats',
    body: 'You are driving. Post the route you are already taking and approve the people who ask for a seat.',
    Icon: WheelIcon,
  },
  {
    mode: 'passenger',
    title: 'Find a ride',
    body: 'You need a lift. Search for drivers going your way and ask one of them for a seat.',
    Icon: SeatIcon,
  },
]

export function RoleSelectionScreen() {
  const user = useCurrentUser()
  const navigate = useNavigate()
  const updateMe = useUpdateMe()

  function choose(mode: Mode) {
    updateMe.mutate(
      { preferences: { default_mode: mode } },
      { onSuccess: () => navigate(homePathFor(mode), { replace: true }) },
    )
  }

  return (
    <div className="mx-auto min-h-dvh w-full max-w-[34rem] px-5 py-8">
      <Wordmark className="text-lg" />

      <h1 className="mt-10 text-2xl">How do you want to start, {user.name.split(' ')[0]}?</h1>
      <p className="mt-3 max-w-[48ch] text-ink-70">
        This only decides which screen opens first. You can switch between driving and riding
        whenever you like.
      </p>

      {updateMe.isError ? (
        <div className="mt-6">
          <ErrorNotice>{messageFor(updateMe.error)}</ErrorNotice>
        </div>
      ) : null}

      <div className="mt-8 flex flex-col gap-4">
        {CHOICES.map(({ mode, title, body, Icon }) => (
          <button
            key={mode}
            type="button"
            disabled={updateMe.isPending}
            onClick={() => choose(mode)}
            className="group flex items-start gap-4 rounded-card border border-hairline bg-surface p-5 text-left transition-colors hover:border-ink disabled:cursor-not-allowed disabled:opacity-60"
          >
            <span className="mt-0.5 text-ink-45 transition-colors group-hover:text-signal-deep">
              <Icon width="28" height="28" />
            </span>
            <span>
              <span className="block text-lg font-semibold">{title}</span>
              <span className="mt-1 block max-w-[46ch] text-sm text-ink-70">{body}</span>
            </span>
          </button>
        ))}
      </div>
    </div>
  )
}
