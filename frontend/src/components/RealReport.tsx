import type { ClarityEstimate, ClarityValues, TranscriptInfo } from '../lib/api'
import { formatTime, validInterval } from '../lib/format'
import type { AnalysisSession } from '../lib/session'
import { categoryLabel } from './FindingsPanel'
import { Card, LiveBadge } from './ui'

const statusLabel = {
  completed: 'Complete, with findings',
  completed_no_findings: 'Complete, no supported findings',
  partial: 'Partial',
} as const

/** `undefined` means the backend did not report provenance at all, which is different from there being no transcript. */
export function describeTranscript(info: TranscriptInfo | null | undefined): string {
  if (info === undefined) return 'Provenance unknown'
  if (!info || info.source === 'none') return 'No transcript'
  if (info.source === 'machine_generated') return 'Recognised by the speech model; not reviewed'
  const unverified = '(not independently verified)'
  if (info.origin) {
    // The shared text: checked against one recording is not checked against the other.
    const vouched = info.attested_for ?? []
    if (vouched.length === 2) return `Provided by you; you stated you checked it against both recordings ${unverified}`
    if (vouched[0] === 'participant') {
      return `Provided by you; you stated you checked it against your recording only, so it has not been checked against the reference ${unverified}`
    }
    if (vouched[0] === 'reference') {
      return `Provided by you; you stated you checked it against the reference recording only, so it has not been checked against yours ${unverified}`
    }
    return 'Provided by you; not reviewed'
  }
  return info.review_status === 'user_attested'
    ? `Provided by you; you stated you checked it against the recording ${unverified}`
    : 'Provided by you; not reviewed'
}

function usedTranscript(result: AnalysisSession['result']): TranscriptInfo | null | undefined {
  return result.transcripts ? (result.transcripts.shared_for_comparison ?? result.transcripts.participant) : undefined
}

/** A printable report of one real analysis: only what the backend measured, found and withheld. */
const clarityRows: { label: string; value: (v: ClarityValues) => string }[] = [
  {
    label: 'Articulation rate (syllables per second, pauses excluded)',
    value: (v) => (v.articulation_rate_syll_per_sec === null ? 'not measured' : v.articulation_rate_syll_per_sec.toFixed(2)),
  },
  {
    label: 'Mean recogniser word confidence (0 to 1)',
    value: (v) => (v.mean_word_confidence === null ? 'no recognised words' : v.mean_word_confidence.toFixed(2)),
  },
  {
    label: 'Words below 0.5 confidence',
    value: (v) => (v.low_confidence_word_share === null ? 'no recognised words' : `${Math.round(v.low_confidence_word_share * 100)}% of ${v.words}`),
  },
]

function ClaritySection({ clarity }: { clarity: ClarityEstimate | null | undefined }) {
  return (
    <section aria-labelledby="real-report-clarity" className="border-b border-line py-5">
      <h3 id="real-report-clarity" className="text-xs font-semibold tracking-widest text-muted uppercase">
        Clarity estimate
      </h3>
      {!clarity || clarity.status === 'unavailable' ? (
        <p className="mt-3 text-sm text-muted">Not available for this analysis.</p>
      ) : (
        <>
          <p className="mt-2 text-xs text-warn">Estimate only, not a finding: accent, voice, microphone and recogniser errors all affect it.</p>
          <table className="mt-3 w-full text-left text-sm">
            <thead className="text-xs text-muted">
              <tr>
                <th scope="col" className="py-1 font-medium">Measure</th>
                <th scope="col" className="py-1 font-medium">This recording</th>
                {clarity.reference && <th scope="col" className="py-1 font-medium">Reference</th>}
              </tr>
            </thead>
            <tbody>
              {clarityRows.map((row) => (
                <tr key={row.label} className="border-t border-line">
                  <th scope="row" className="py-1.5 pr-3 font-normal">{row.label}</th>
                  <td className="py-1.5 font-mono">{row.value(clarity.participant)}</td>
                  {clarity.reference && <td className="py-1.5 font-mono">{row.value(clarity.reference)}</td>}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-3 text-xs text-muted">{clarity.method}</p>
        </>
      )}
    </section>
  )
}

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
            <dd>{describeTranscript(usedTranscript(result))}</dd>
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
                  {validInterval(finding.start, finding.end, features.audio.duration_sec) ?? 'Interval unavailable'} ·{' '}
                  {categoryLabel[finding.category]} ·{' '}
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

      <ClaritySection clarity={result.clarity} />

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
