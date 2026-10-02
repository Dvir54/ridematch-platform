import { useState } from 'react'
import { Link } from 'react-router-dom'
import { messageFor } from '../../api/errors'
import { useAdminUsers } from '../../api/hooks/admin'
import { SelectField, TextField } from '../../components/Field'
import { EmptyState, InlineLoader, LoadFailure } from '../../components/states'
import { paths } from '../../routes'
import { LIMIT, Pager } from './Pager'

type ActiveFilter = 'all' | 'active' | 'deactivated'

function activeParam(filter: ActiveFilter): boolean | undefined {
  if (filter === 'active') return true
  if (filter === 'deactivated') return false
  return undefined
}

export function AdminUsersScreen() {
  const [q, setQ] = useState('')
  const [activeFilter, setActiveFilter] = useState<ActiveFilter>('all')
  const [offset, setOffset] = useState(0)

  const users = useAdminUsers({
    q: q.trim() || undefined,
    is_active: activeParam(activeFilter),
    limit: LIMIT,
    offset,
  })

  return (
    <>
      <div className="mb-5 flex flex-wrap gap-3">
        <div className="min-w-[14rem] flex-1">
          <TextField
            label="Search"
            placeholder="Name or email"
            value={q}
            onChange={(event) => {
              setQ(event.target.value)
              setOffset(0)
            }}
          />
        </div>
        <div className="w-40">
          <SelectField
            label="Status"
            value={activeFilter}
            onChange={(event) => {
              setActiveFilter(event.target.value as ActiveFilter)
              setOffset(0)
            }}
          >
            <option value="all">All</option>
            <option value="active">Active</option>
            <option value="deactivated">Deactivated</option>
          </SelectField>
        </div>
      </div>

      {users.isPending ? <InlineLoader label="Loading users" /> : null}

      {users.isError ? (
        <LoadFailure
          title="Users did not load"
          message={messageFor(users.error)}
          onRetry={() => void users.refetch()}
        />
      ) : null}

      {users.data?.data.length === 0 ? (
        <EmptyState title="No users match" body="Try a different search or clear the filters." />
      ) : null}

      <ul className="flex flex-col gap-3">
        {users.data?.data.map((user) => (
          <li key={user.id}>
            <Link
              to={paths.adminUser(user.id)}
              className="block rounded-card border border-hairline bg-surface p-4 hover:border-ink"
            >
              <div className="flex items-center justify-between gap-3">
                <p className="font-semibold">{user.name}</p>
                <div className="flex gap-1.5">
                  {user.is_admin ? (
                    <span className="rounded-full border border-ink/25 px-2.5 py-0.5 text-xs font-semibold">
                      Admin
                    </span>
                  ) : null}
                  <span
                    className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold ${
                      user.is_active
                        ? 'border-go/40 bg-go/10 text-go'
                        : 'border-alert/30 bg-alert-wash text-alert'
                    }`}
                  >
                    {user.is_active ? 'Active' : 'Deactivated'}
                  </span>
                </div>
              </div>
              <p className="mt-1 text-sm text-ink-70">{user.email}</p>
            </Link>
          </li>
        ))}
      </ul>

      {users.data ? (
        <Pager offset={offset} total={users.data.total} onChange={setOffset} />
      ) : null}
    </>
  )
}
