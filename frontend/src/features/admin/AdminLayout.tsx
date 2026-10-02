import { NavLink, Outlet } from 'react-router-dom'
import { TabHeader } from '../../components/TabHeader'
import { paths } from '../../routes'

const TABS = [
  { to: paths.adminUsers, label: 'Users' },
  { to: paths.adminRides, label: 'Rides' },
  { to: paths.adminAnalytics, label: 'Analytics' },
]

/**
 * The three admin sections share one tab strip rather than the bottom nav,
 * because admin isn't a riding mode (CONTRACT §2: `is_admin` is a DB flag, not
 * a `Mode`) — it's reached from Profile and stays out of the driver/passenger
 * tabs everyone else uses.
 */
export function AdminLayout() {
  return (
    <>
      <TabHeader
        title="Admin"
        lead="User management, ride monitoring and platform analytics. The backend enforces this too, so nobody but an admin ever sees it."
      />

      <nav aria-label="Admin sections" className="mb-6 flex gap-2">
        {TABS.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            className={({ isActive }) =>
              `rounded-full border px-3 py-1 text-sm font-semibold ${
                isActive
                  ? 'border-ink bg-ink text-surface'
                  : 'border-hairline text-ink-70 hover:border-ink hover:text-ink'
              }`
            }
          >
            {tab.label}
          </NavLink>
        ))}
      </nav>

      <Outlet />
    </>
  )
}
