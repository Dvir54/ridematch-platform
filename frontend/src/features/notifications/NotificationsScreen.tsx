import { messageFor } from '../../api/errors'
import {
  useClearNotifications,
  useMarkAllNotificationsRead,
  useMarkNotificationRead,
  useNotifications,
} from '../../api/hooks/notifications'
import type { Notification } from '../../api/types'
import { Button } from '../../components/Button'
import { ConfirmAction } from '../../components/ConfirmAction'
import { TabHeader } from '../../components/TabHeader'
import { EmptyState, ErrorNotice, InlineLoader, LoadFailure } from '../../components/states'
import { formatDateTime } from '../../lib/dates'

function NotificationRow({ notification }: { notification: Notification }) {
  const markRead = useMarkNotificationRead()

  return (
    <li
      className={`rounded-card border p-4 ${
        notification.is_read ? 'border-hairline bg-surface' : 'border-ink/25 bg-paper'
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-semibold">{notification.title}</p>
          <p className="mt-1 text-sm text-ink-70">{notification.message}</p>
          <p className="tnum mt-2 text-xs text-ink-45">
            {formatDateTime(notification.created_at)}
          </p>
        </div>
        {!notification.is_read ? (
          <Button
            variant="quiet"
            disabled={markRead.isPending}
            onClick={() => markRead.mutate(notification.id)}
          >
            Mark read
          </Button>
        ) : null}
      </div>
      {markRead.isError && markRead.variables === notification.id ? (
        <p className="mt-2 text-xs text-alert">{messageFor(markRead.error)}</p>
      ) : null}
    </li>
  )
}

export function NotificationsScreen() {
  const notifications = useNotifications()
  const markAllRead = useMarkAllNotificationsRead()
  const clearAll = useClearNotifications()

  const hasUnread = notifications.data?.some((row) => !row.is_read) ?? false

  return (
    <>
      <TabHeader
        title="Alerts"
        lead="Seat requests, approvals, cancellations and departure reminders, live while you have RideMatch open."
      />

      {notifications.isPending ? <InlineLoader label="Loading alerts" /> : null}

      {notifications.isError ? (
        <LoadFailure
          title="Alerts did not load"
          message={messageFor(notifications.error)}
          onRetry={() => void notifications.refetch()}
        />
      ) : null}

      {notifications.data?.length === 0 ? (
        <EmptyState
          title="No alerts"
          body="Seat requests, approvals, cancellations and departure reminders arrive here, live, while you have RideMatch open."
        />
      ) : null}

      {notifications.data?.length ? (
        <div className="mb-5 flex flex-col gap-3">
          {markAllRead.isError ? <ErrorNotice>{messageFor(markAllRead.error)}</ErrorNotice> : null}
          {clearAll.isError ? <ErrorNotice>{messageFor(clearAll.error)}</ErrorNotice> : null}
          <div className="flex flex-wrap gap-2">
            <Button
              variant="secondary"
              disabled={!hasUnread || markAllRead.isPending}
              onClick={() => markAllRead.mutate()}
            >
              {markAllRead.isPending ? 'Marking…' : 'Mark all read'}
            </Button>
            <ConfirmAction
              label="Clear all"
              question="This deletes every alert. It cannot be undone."
              confirmLabel="Delete them all"
              pending={clearAll.isPending}
              onConfirm={() => clearAll.mutate()}
            />
          </div>
        </div>
      ) : null}

      {notifications.data?.length ? (
        <ul className="flex flex-col gap-3">
          {notifications.data.map((notification) => (
            <NotificationRow key={notification.id} notification={notification} />
          ))}
        </ul>
      ) : null}
    </>
  )
}
