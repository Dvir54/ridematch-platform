export function TabHeader({ title, lead }: { title: string; lead?: string }) {
  return (
    <div className="mb-6">
      <h1 className="text-xl">{title}</h1>
      {lead ? <p className="mt-2 max-w-[52ch] text-ink-70">{lead}</p> : null}
    </div>
  )
}
