import { formatInterval, formatPercent } from '../lib/format'
import type { Finding } from '../types'
import { EmptyState, EvidenceKindBadge, SeverityBadge } from './ui'

export function FindingList({
  findings,
  selectedId,
  onSelect,
}: {
  findings: Finding[]
  selectedId: string | null
  onSelect: (id: string) => void
}) {
  if (findings.length === 0) {
    return (
      <EmptyState
        title="No findings to show"
        description="No flaw intervals match. Either the delivery is close to the baseline or the current filter hides them."
      />
    )
  }

  return (
    <ul className="flex flex-col gap-2">
      {findings.map((finding) => {
        const selected = finding.id === selectedId
        return (
          <li key={finding.id}>
            <button
              type="button"
              onClick={() => onSelect(finding.id)}
              aria-pressed={selected}
              className={`w-full rounded-lg border p-4 text-left transition-colors ${
                selected ? 'border-accent/60 bg-ink-700' : 'border-line bg-ink-900 hover:border-muted/50'
              }`}
            >
              <span className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-sm font-semibold">{finding.title}</span>
                <SeverityBadge severity={finding.severity} />
              </span>
              <span className="mt-1.5 block font-mono text-xs text-muted">
                {formatInterval(finding.interval)} · confidence {formatPercent(finding.confidence)}
              </span>
              <span className="mt-2 block text-sm text-muted">{finding.summary}</span>
            </button>
          </li>
        )
      })}
    </ul>
  )
}

/** Evidence, confidence and limitations for one finding. */
export function FindingDetail({ finding }: { finding: Finding }) {
  const lowConfidence = finding.confidence < 0.6
  return (
    <div className="animate-rise" key={finding.id}>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-lg font-semibold">{finding.title}</h3>
        <SeverityBadge severity={finding.severity} />
      </div>
      <p className="mt-1 font-mono text-xs text-muted">
        {formatInterval(finding.interval)} · confidence {formatPercent(finding.confidence)}
        {lowConfidence && <span className="text-warn"> · low confidence</span>}
      </p>
      <blockquote className="mt-4 border-l-2 border-line pl-3 text-sm text-muted italic">
        {finding.transcriptExcerpt}
      </blockquote>

      <h4 className="mt-5 text-xs font-semibold tracking-widest text-muted uppercase">Evidence</h4>
      <ul className="mt-2 flex flex-col gap-2">
        {finding.evidence.map((item) => (
          <li key={`${item.kind}-${item.label}`} className="rounded-lg border border-line bg-ink-900 p-3">
            <div className="flex flex-wrap items-center gap-2">
              <EvidenceKindBadge kind={item.kind} />
              <span className="text-sm font-medium">{item.label}</span>
            </div>
            {(item.participant || item.baseline) && (
              <dl className="mt-2 grid grid-cols-2 gap-2 text-sm">
                <div>
                  <dt className="text-xs text-muted">Participant</dt>
                  <dd className="font-mono">{item.participant ?? '—'}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted">Baseline</dt>
                  <dd className="font-mono">{item.baseline ?? '—'}</dd>
                </div>
              </dl>
            )}
            {item.detail && <p className="mt-2 text-sm text-muted">{item.detail}</p>}
          </li>
        ))}
      </ul>

      <h4 className="mt-5 text-xs font-semibold tracking-widest text-muted uppercase">Limitations</h4>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted">
        {finding.limitations.map((limitation) => (
          <li key={limitation}>{limitation}</li>
        ))}
      </ul>
    </div>
  )
}
