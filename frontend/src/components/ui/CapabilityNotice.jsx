export default function CapabilityNotice({ children = 'This is read-only in the guest demo. Connect Spotify to use this action.' }) {
  return (
    <div className="rounded-lg border border-brand/20 bg-brand/5 px-3 py-2 text-xs text-zinc-300">
      {children}
    </div>
  )
}
