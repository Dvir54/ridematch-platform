import { EmptyState } from '../../components/states'
import { TabHeader } from '../../components/TabHeader'

export function NotificationsScreen() {
  return (
    <>
      <TabHeader title="Alerts" />
      <EmptyState
        title="No alerts"
        body="Seat requests, approvals, cancellations and departure reminders arrive here, live, while you have RideMatch open."
      />
    </>
  )
}
