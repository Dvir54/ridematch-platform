import { NavLink } from 'react-router-dom'
import type { Mode } from '../api/types'
import { paths } from '../routes'
import { BellIcon, BoardIcon, InboxIcon, PersonIcon, SearchIcon, SeatIcon, WheelIcon } from './icons'

interface NavItem {
  to: string
  label: string
  Icon: typeof BoardIcon
  end?: boolean
}

const SHARED: NavItem[] = [
  { to: paths.notifications, label: 'Alerts', Icon: BellIcon },
  { to: paths.profile, label: 'Profile', Icon: PersonIcon },
]

const BY_MODE: Record<Mode, NavItem[]> = {
  driver: [
    { to: paths.driverHome, label: 'Home', Icon: WheelIcon, end: true },
    { to: paths.driverRides, label: 'My rides', Icon: BoardIcon },
    { to: paths.driverRequests, label: 'Requests', Icon: InboxIcon },
    ...SHARED,
  ],
  passenger: [
    { to: paths.passengerHome, label: 'Home', Icon: SeatIcon, end: true },
    { to: paths.passengerSearch, label: 'Search', Icon: SearchIcon },
    { to: paths.passengerTrips, label: 'My trips', Icon: BoardIcon },
    ...SHARED,
  ],
}

export function BottomNav({ mode }: { mode: Mode }) {
  return (
    <nav
      aria-label="Main"
      className="fixed inset-x-0 bottom-0 border-t border-hairline bg-surface pb-[env(safe-area-inset-bottom)]"
    >
      <ul className="mx-auto flex max-w-[34rem]">
        {BY_MODE[mode].map(({ to, label, Icon, end }) => (
          <li key={to} className="flex-1">
            <NavLink
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex flex-col items-center gap-1 border-t-2 px-1 pt-2.5 pb-2 text-xs font-medium ${
                  isActive ? 'border-ink text-ink' : 'border-transparent text-ink-45'
                }`
              }
            >
              <Icon width="20" height="20" />
              {label}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  )
}
