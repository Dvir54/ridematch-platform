export interface StatItem {
  label: string
  value: number
}

/** A row of plain counters — Home's at-a-glance numbers and Profile's full trip record. */
export function StatsGrid({ items }: { items: StatItem[] }) {
  return (
    <dl className="grid grid-cols-3 gap-3">
      {items.map((item) => (
        <div key={item.label} className="rounded-card border border-hairline bg-surface px-3 py-3 text-center">
          <dd className="tnum text-xl font-semibold">{item.value}</dd>
          <dt className="mt-0.5 text-xs text-ink-70">{item.label}</dt>
        </div>
      ))}
    </dl>
  )
}
