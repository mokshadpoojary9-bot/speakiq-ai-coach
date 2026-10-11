import { useEffect, useState } from 'react'
import { fetchHealth, type HealthResponse } from '../lib/api'

type State =
  | { kind: 'loading' }
  | { kind: 'online'; health: HealthResponse }
  | { kind: 'offline' }

/** Live backend status. Reports only what GET /health actually returned. */
export function HealthStatus() {
  const [state, setState] = useState<State>({ kind: 'loading' })

  useEffect(() => {
    const controller = new AbortController()
    fetchHealth(controller.signal)
      .then((health) => setState({ kind: 'online', health }))
      .catch(() => {
        if (!controller.signal.aborted) setState({ kind: 'offline' })
      })
    return () => controller.abort()
  }, [])

  const dot =
    state.kind === 'online' ? 'bg-accent' : state.kind === 'offline' ? 'bg-warn' : 'bg-muted'
  const text =
    state.kind === 'online'
      ? `Backend online (v${state.health.version})`
      : state.kind === 'offline'
        ? 'Backend not reachable'
        : 'Checking backend…'

  return (
    <span role="status" className="inline-flex items-center gap-2 text-xs text-muted">
      <span aria-hidden="true" className={`h-2 w-2 rounded-full ${dot}`} />
      {text}
    </span>
  )
}
