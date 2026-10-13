import type { AnalysisSession } from '../lib/session'
import { formatTime } from '../lib/format'
import { categoryLabel } from './FindingsPanel'
import { Badge, Card, EmptyState } from './ui'

/** Rule-based coaching the backend built from this recording's findings. No language model is involved. */
export function RealCoach({ session }: { session: AnalysisSession }) {
  const { result } = session
  const byId = new Map(result.findings.map((finding) => [finding.id, finding]))
  const tips = result.coaching ?? []

  if (tips.length === 0) {
    return (
      <EmptyState
        title={result.status === 'partial' ? 'No coaching: the analysis was only partial' : 'No coaching for this recording'}
        description={
          result.status === 'partial'
            ? 'Coaching is only written from findings, and part of the analysis could not run. The dashboard lists what was withheld and why.'
            : 'Coaching is only written from findings, and no rule found a difference that crossed its threshold. That is not a rating of the delivery.'
        }
      />
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted">
        Each suggestion is fixed wording chosen by the rule that produced the findings, with the measurements quoted
        from them. It does not say why a difference happened, and a difference is not necessarily a fault.
      </p>
      <ol aria-label="Coaching suggestions" className="flex flex-col gap-4">
        {tips.map((tip) => (
          <li key={tip.id}>
            <Card as="article">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-lg font-semibold">{tip.action}</h2>
                <Badge>{categoryLabel[tip.category]}</Badge>
                <Badge>Rule-based · no language model</Badge>
              </div>
              {tip.caution && (
                <p role="note" className="mt-3 rounded-lg border border-warn/40 bg-warn/5 px-3 py-2 text-sm text-warn">
                  {tip.caution}
                </p>
              )}
              <h3 className="mt-4 text-xs font-semibold tracking-widest text-muted uppercase">Try this</h3>
              <p className="mt-1 text-sm">{tip.practice}</p>
              <h3 className="mt-4 text-xs font-semibold tracking-widest text-muted uppercase">Based on</h3>
              <p className="mt-1 text-sm text-muted">{tip.based_on}</p>
              <ul className="mt-3 flex flex-wrap gap-2" aria-label="Findings behind this suggestion">
                {tip.finding_ids.map((id) => {
                  const finding = byId.get(id)
                  return (
                    finding && (
                      <li key={id} className="rounded-md border border-line bg-ink-900 px-2 py-1 font-mono text-xs text-muted">
                        {formatTime(finding.start)} – {formatTime(finding.end)}
                      </li>
                    )
                  )
                })}
              </ul>
            </Card>
          </li>
        ))}
      </ol>
    </div>
  )
}
