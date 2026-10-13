import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAnalysisSession, type AnalysisSession } from '../lib/session'

export type Source = 'live' | 'demo'

/** Which data a page shows: the real analysis from this session if there is one, otherwise the demo fixture. */
export function useSource(): { source: Source; session: AnalysisSession | null; setSource: (source: Source) => void } {
  const { session } = useAnalysisSession()
  const [preferred, setSource] = useState<Source>('live')
  return { source: session && preferred === 'live' ? 'live' : 'demo', session, setSource }
}

const toggleClass = (active: boolean) =>
  `rounded-md px-3 py-1.5 text-sm transition-colors ${active ? 'bg-ink-700 text-accent' : 'text-muted hover:text-fg'}`

/** Lets the viewer flip between their recording and the demo, or tells them how to get a real analysis. */
export function SourceSwitch({
  source,
  hasSession,
  onChange,
}: {
  source: Source
  hasSession: boolean
  onChange: (source: Source) => void
}) {
  if (!hasSession) {
    return (
      <p className="mb-6 rounded-lg border border-line bg-ink-800 px-4 py-3 text-sm text-muted">
        No recording has been analysed in this session, so this page shows the demo fixture.{' '}
        <Link to="/workspace" className="font-medium text-accent underline underline-offset-2">
          Analyse a recording
        </Link>{' '}
        to see real measurements here.
      </p>
    )
  }
  return (
    <div role="group" aria-label="Data source" className="mb-6 inline-flex rounded-lg border border-line bg-ink-900 p-1">
      <button type="button" className={toggleClass(source === 'live')} aria-pressed={source === 'live'} onClick={() => onChange('live')}>
        Your recording
      </button>
      <button type="button" className={toggleClass(source === 'demo')} aria-pressed={source === 'demo'} onClick={() => onChange('demo')}>
        Demo fixture
      </button>
    </div>
  )
}
