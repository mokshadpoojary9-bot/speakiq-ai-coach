import type { TranscriptInfo } from '../lib/api'
import { formatTime } from '../lib/format'
import type { AnalysisSession } from '../lib/session'
import { categoryLabel } from './FindingsPanel'
import { Card, LiveBadge } from './ui'

const statusLabel = {
  completed: 'Complete, with findings',
  completed_no_findings: 'Complete, no supported findings',
  partial: 'Partial',
} as const

export function describeTranscript(info: TranscriptInfo | null): string {
  if (!info || info.source === 'none') return 'No transcript'
  if (info.source === 'machine_generated') return 'Recognised by the speech model; not reviewed'
  return info.review_status === 'user_attested'
    ? 'Provided by you; you stated you checked it against the recording (not independently verified)'
    : 'Provided by you; not reviewed'
}

/** A printable report of one real analysis: only what the backend measured, found and withheld. */
export function RealReport({ session }: { session: AnalysisSession }) {
  const { result, analysedAt } = session
  const { features, findings, rules } = result
  const withheld = rules.filter((rule) => rule.status === 'withheld' || rule.status === 'not_supported')
  const tips = result.coaching ?? []

  return (
    <Card as="article" aria-labelledby="real-report-title" className="mx-auto max-w-4xl">
      <header className="border-b border-line pb-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 id="real-report-title" className="text-2xl font-semibold">
              Speech delivery report
            </h2>
            <p className="mt-1 font-mono text-xs text-muted">
              {features.audio.filename} · {formatTime(features.audio.duration_sec)} · analysed {analysedAt.toLocaleString()}
            </p>
          </div>
          <LiveBadge filename={features.audio.filename} />
        </div>
        <dl className="mt-4 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-xs text-muted">Analysis status</dt>
            <dd>{statusLabel[result.status]}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted">Reference recording</dt>
            <dd>
              {result.alignment_status.status === 'aligned'
                ? `${result.reference?.filename ?? 'Reference'}, ${result.alignment_status.words_compared} of ${result.alignment_status.transcript_word_count} words compared`
                : result.alignment_status.status === 'unavailable'
                  ? `Not used: ${result.alignment_status.reason}`
                  : 'None'}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted">Transcript</dt>
            <dd>{describeTranscript(result.transcripts.shared_for_comparison ?? result.transcripts.participant)}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted">Recording quality</dt>
            <dd>
              {result.signal_quality.issues.length === 0
                ? 'No problems detected'
                : result.signal_quality.issues.map((issue) => issue.message).join(' ')}
            </dd>
          </div>
        </dl>
      </header>

      <section aria-labelledby="real-report-findings" className="border-b border-line py-5">
        <h3 id="real-report-findings" className="text-xs font-semibold tracking-widest text-muted uppercase">
          Findings ({findings.length})
        </h3>
        {findings.length === 0 ? (
          <p className="mt-3 text-sm text-muted">
            {result.status === 'partial'
              ? 'No findings could be established because part of the analysis did not run. This is not a statement that the delivery was checked and found fine.'
              : 'No rule found a difference that crossed its threshold. This does not rate the delivery as good.'}
          </p>
        ) : (
          <ol className="mt-3 flex flex-col gap-3">
            {findings.map((finding, index) => (
              <li key={finding.id} className="rounded-lg border border-line bg-ink-900 p-4">
                <h4 className="text-base font-semibold">
                  {index + 1}. {finding.title}
                </h4>
                <p className="mt-1 font-mono text-xs text-muted">
                  {formatTime(finding.start)} – {formatTime(finding.end)} · {categoryLabel[finding.category]} ·{' '}
                  {finding.severity ? `${finding.severity} difference` : 'no severity'} · {finding.evidence_quality} evidence quality
                </p>
                <p className="mt-2 text-sm">{finding.explanation}</p>
              </li>
            ))}
          </ol>
        )}
      </section>

      <section aria-labelledby="real-report-coaching" className="border-b border-line py-5">
        <h3 id="real-report-coaching" className="text-xs font-semibold tracking-widest text-muted uppercase">
          Suggestions ({tips.length})
        </h3>
        {tips.length === 0 ? (
          <p className="mt-3 text-sm text-muted">None. Suggestions are only written from findings.</p>
        ) : (
          <ul className="mt-3 flex flex-col gap-2 text-sm">
            {tips.map((tip) => (
              <li key={tip.id} className="border-l-2 border-accent/50 pl-3">
                <span className="font-medium">{tip.action}</span> <span className="text-muted">{tip.practice}</span>
                {tip.caution && <span className="block text-warn">{tip.caution}</span>}
              </li>
            ))}
          </ul>
        )}
        <p className="mt-3 text-xs text-muted">Rule-based wording; no language model was used.</p>
      </section>

      {withheld.length > 0 && (
        <section aria-labelledby="real-report-withheld" className="border-b border-line py-5">
          <h3 id="real-report-withheld" className="text-xs font-semibold tracking-widest text-muted uppercase">
            Not checked
          </h3>
          <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-muted">
            {withheld.map((rule) => (
              <li key={`${rule.rule_id}-${rule.category}`}>
                <span className="text-fg">{categoryLabel[rule.category]}:</span> {rule.reason}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section aria-labelledby="real-report-limitations" className="pt-5">
        <h3 id="real-report-limitations" className="text-xs font-semibold tracking-widest text-muted uppercase">
          Limitations
        </h3>
        <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-muted">
          {result.limitations.map((limitation) => (
            <li key={limitation}>{limitation}</li>
          ))}
        </ul>
      </section>
    </Card>
  )
}
