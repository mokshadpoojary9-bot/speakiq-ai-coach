import type { AnalysisSession } from '../lib/session'
import { validInterval } from '../lib/format'
import { categoryLabel } from './FindingsPanel'
import { Badge, Card, EmptyState } from './ui'

const number = (value: number | null | undefined) => (value === null || value === undefined ? '—' : String(Number(value.toFixed(2))))

/** What the rules could not assess for this recording, so an absent suggestion is not read as "fine". */
function NotAssessed({ session }: { session: AnalysisSession }) {
  const missing = session.result.rules.filter((rule) => rule.status === 'withheld' || rule.status === 'not_supported')
  if (missing.length === 0) return null
  return (
    <section aria-labelledby="not-assessed-heading" className="rounded-xl border border-line bg-ink-800 p-5">
      <h2 id="not-assessed-heading" className="text-sm font-semibold">
        Could not be assessed
      </h2>
      <p className="mt-1 text-sm text-muted">
        No suggestion is given for these, because the measurement was unavailable or unreliable, or no defensible
        method exists. That is not a sign that they are fine.
      </p>
      <ul aria-label="Not assessed" className="mt-3 flex flex-col gap-1.5 text-sm">
        {missing.map((rule) => (
          <li key={`${rule.rule_id}-${rule.category}`}>
            <span className="font-medium">{categoryLabel[rule.category]}</span>{' '}
            <span className="text-muted">
              {rule.status === 'not_supported' ? '· not supported' : '· not measurable here'}: {rule.reason}
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}

/** Rule-based coaching the backend built from this recording's findings. No language model is involved. */
export function RealCoach({ session }: { session: AnalysisSession }) {
  const { result } = session
  const byId = new Map(result.findings.map((finding) => [finding.id, finding]))
  const tips = result.coaching ?? []
  const duration = result.features.audio.duration_sec

  if (tips.length === 0) {
    return (
      <div className="flex flex-col gap-4">
        <EmptyState
          title={result.status === 'partial' ? 'No coaching: the analysis was only partial' : 'No coaching for this recording'}
          description={
            result.status === 'partial'
              ? 'Coaching is only written from findings, and part of the analysis could not run. The dashboard lists what was withheld and why.'
              : 'Coaching is only written from findings, and no rule found a difference that crossed its threshold. That is not a rating of the delivery.'
          }
        />
        <NotAssessed session={session} />
      </div>
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
                {tip.certainty && (
                  <Badge tone={tip.certainty === 'confirmed' ? 'accent' : 'warn'}>
                    {tip.certainty === 'confirmed' ? 'Confirmed by measurement' : 'Uncertain'}
                  </Badge>
                )}
                <Badge>Rule-based · no language model</Badge>
              </div>
              {tip.caution && (
                <p role="note" className="mt-3 rounded-lg border border-warn/40 bg-warn/5 px-3 py-2 text-sm text-warn">
                  {tip.caution}
                </p>
              )}
              <h3 className="mt-4 text-xs font-semibold tracking-widest text-muted uppercase">Try this</h3>
              <p className="mt-1 text-sm">{tip.practice}</p>
              {tip.reason && (
                <>
                  <h3 className="mt-4 text-xs font-semibold tracking-widest text-muted uppercase">Why this is suggested</h3>
                  <p className="mt-1 text-sm">{tip.reason}</p>
                </>
              )}
              <h3 className="mt-4 text-xs font-semibold tracking-widest text-muted uppercase">Based on</h3>
              <p className="mt-1 text-sm text-muted">{tip.based_on}</p>
              {tip.evidence && tip.evidence.length > 0 && (
                <table className="mt-3 w-full text-left text-sm">
                  <caption className="sr-only">Measurements behind: {tip.action}</caption>
                  <thead className="text-xs text-muted">
                    <tr>
                      <th scope="col" className="py-1 pr-3 font-medium">When</th>
                      <th scope="col" className="py-1 pr-3 font-medium">Measurement</th>
                      <th scope="col" className="py-1 pr-3 font-medium">You</th>
                      <th scope="col" className="py-1 pr-3 font-medium">Reference</th>
                      <th scope="col" className="py-1 pr-3 font-medium">Difference</th>
                      <th scope="col" className="py-1 font-medium">Evidence</th>
                    </tr>
                  </thead>
                  <tbody className="font-mono text-xs">
                    {tip.evidence.map((item) => (
                      <tr key={item.finding_id} className="border-t border-line">
                        <td className="py-1 pr-3">{validInterval(item.start, item.end, duration) ?? 'interval unavailable'}</td>
                        <td className="py-1 pr-3 font-sans">
                          {item.feature.replaceAll('_', ' ')} ({item.unit})
                        </td>
                        <td className="py-1 pr-3">{number(item.participant_value)}</td>
                        <td className="py-1 pr-3">{item.reference_value === null ? 'no reference' : number(item.reference_value)}</td>
                        <td className="py-1 pr-3">{number(item.difference)}</td>
                        <td className="py-1 font-sans">{item.evidence_quality}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              <ul className="mt-3 flex flex-wrap gap-2" aria-label="Findings behind this suggestion">
                {tip.finding_ids.map((id) => {
                  const finding = byId.get(id)
                  return (
                    finding && (
                      <li key={id} className="rounded-md border border-line bg-ink-900 px-2 py-1 font-mono text-xs text-muted">
                        {validInterval(finding.start, finding.end, duration) ?? 'interval unavailable'}
                      </li>
                    )
                  )
                })}
              </ul>
            </Card>
          </li>
        ))}
      </ol>
      <NotAssessed session={session} />
    </div>
  )
}
