import { useEffect, useState } from 'react'

export function formatCountdown(secs: number): string {
  const s = Math.floor(secs)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const ss = s % 60
  if (h > 0) return `${h}h ${m}m`
  return `${m}:${String(ss).padStart(2, '0')}`
}

interface Props {
  target: number // epoch seconds, server clock
  serverTime: number // server clock when status was fetched
  fetchedAt: number // local clock (epoch seconds) when status was fetched
}

/** Self-ticking countdown — keeps the 1 s re-render confined to this leaf
 *  component instead of re-rendering the whole app (and 150 table rows). */
export default function Countdown({ target, serverTime, fetchedAt }: Props) {
  const [now, setNow] = useState(() => Date.now() / 1000)

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now() / 1000), 1000)
    return () => clearInterval(id)
  }, [])

  const remaining = Math.max(0, target - serverTime - (now - fetchedAt))
  return <>{formatCountdown(remaining)}</>
}
