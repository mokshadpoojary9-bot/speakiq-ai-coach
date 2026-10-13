import type { AnalyzeResponse, DetectedFinding, FindingCategory, RuleReport } from '../lib/api'
import { formatTime } from '../lib/format'
import { Badge, EmptyState } from './ui'

export const categoryLabel: Record<FindingCategory, string> = {
  rushed_delivery: 'Rushed delivery',
  slow_delivery: 'Slow delivery',
  excessive_pause: 'Pauses',
  irregular_pauses: 'Pause placement',
  filler_word: 'Filler words',
  uneven_pacing: 'Uneven pacing',
  pitch_monotony: 'Pitch variation',
  unclear_articulation: 'Articulation',
}

export const categoryColor: Record<FindingCategory, string> = {
  rushed_delivery: '#f07f7a',
  slow_delivery: '#e5b454',
  excessive_pause: '#8fb8d8',
  irregular_pauses: '#6f9fe0',
  filler_word: '#c59be8',
  uneven_pacing: '#e5b454',
  pitch_monotony: '#7fd1c7',
  unclear_articulation: '#9fada6',
}

const statusText: Record<AnalyzeResponse['status'], { title: string; detail: string; tone: 'accent' | 'warn' }> = {
  completed: {
    title: 'Analysis complete, with findings',
    detail: 'Each finding below is a measured difference that crossed a documented threshold.',
    tone: 'accent',
  },
  completed_no_findings: {
    title: 'Analysis complete: no supported findings',
    detail: 'Every rule that could run was checked and nothing crossed its threshold. That is a result, not a failure.',
    tone: 'accent',
  },
  partial: {
    title: 'Partial analysis',
    detail: 'Some of the analysis could not run for this recording. What was withheld, and why, is listed below.',
    tone: 'warn',
  },
}

const ruleStatusLabel: Record<RuleReport['status'], string> = {
  triggered: 'Found',
  not_triggered: 'Checked, nothing found',
  withheld: 'Could not check',
  not_supported: 'Not supported',
}

const number = (value: number | null) => (value === null ? '—' : String(Number(value.toFixed(2))))

function FindingCard({ finding, onSeek }: { finding: DetectedFinding; onSeek?: (time: number) => void }) {
  const interval = `${formatTime(finding.start)} – ${formatTime(finding.end)}`
  return (
    <li className="rounded-lg border border-line bg-ink-900 p-4" style={{ borderLeftColor: categoryColor[finding.category], borderLeftWidth: 3 }}>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-base font-semibold">{finding.title}</h3>
        <Badge>{categoryLabel[finding.category]}</Badge>
        {finding.severity ? <Badge tone="warn">{finding.severity} difference</Badge> : <Badge>no severity</Badge>}
        <Badge tone={finding.evidence_quality === 'low' ? 'warn' : 'neutral'}>{finding.evidence_quality} evidence quality</Badge>
      </div>
      <p className="mt-1 font-mono text-xs text-muted">
        {onSeek ? (
          <button type="button" className="rounded underline underline-offset-2 hover:text-accent" onClick={() => onSeek(finding.start)} aria-label={`Play from ${interval}`}>
            {interval}
          </button>
        ) : (
          interval
        )}
        {finding.reference_interval &&
          ` · reference ${formatTime(finding.reference_interval.start)} – ${formatTime(finding.reference_interval.end)}`}
      </p>
      <p className="mt-2 text-sm">{finding.explanation}</p>

      <table className="mt-3 w-full text-left text-sm">
        <caption className="sr-only">Measured evidence for {finding.title}</caption>
        <thead className="text-xs text-muted">
          <tr>
            <th scope="col" className="py-1 pr-3 font-medium">Measurement</th>
            <th scope="col" className="py-1 pr-3 font-medium">You</th>
            <th scope="col" className="py-1 pr-3 font-medium">Reference</th>
            <th scope="col" className="py-1 font-medium">Unit</th>
          </tr>
        </thead>
        <tbody className="font-mono text-xs">
          {finding.evidence.map((item) => (
            <tr key={item.feature} className="border-t border-line">
              <th scope="row" className="py-1 pr-3 font-sans font-normal">{item.feature.replaceAll('_', ' ')}</th>
              <td className="py-1 pr-3">{number(item.participant_value)}</td>
              <td className="py-1 pr-3">{number(item.reference_value)}</td>
              <td className="py-1">{item.unit}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <details className="mt-3 text-sm text-muted">
        <summary className="cursor-pointer rounded text-xs font-medium">Method, rule and limitations</summary>
        <p className="mt-2">{finding.comparison_method}</p>
        <p className="mt-2">
          Rule <span className="font-mono text-xs">{finding.rule.rule_id}</span>: {finding.rule.description}{' '}
          <span className="font-mono text-xs">
            ({Object.entries(finding.rule.thresholds).map(([key, value]) => `${key} = ${value}`).join(', ')})
          </span>
        </p>
        {finding.severity_basis && <p className="mt-2">Severity: {finding.severity_basis}</p>}
        <ul className="mt-2 list-disc space-y-1 pl-5">
          {finding.limitations.map((limitation) => (
            <li key={limitation}>{limitation}</li>
          ))}
        </ul>
      </details>
    </li>
  )
}

/** Findings, the rules that were checked, and what was withheld, exactly as the backend reported them. */
export function FindingsPanel({ result, onSeek }: { result: AnalyzeResponse; onSeek?: (time: number) => void }) {
  const status = statusText[result.status]
  const alignment = result.alignment_status
  return (
    <div className="flex flex-col gap-5">
      <div role="status" className={`rounded-lg border px-4 py-3 ${status.tone === 'warn' ? 'border-warn/40 bg-warn/5' : 'border-accent/30 bg-accent/5'}`}>
        <p className={`text-sm font-semibold ${status.tone === 'warn' ? 'text-warn' : 'text-accent'}`}>{status.title}</p>
        <p className="mt-1 text-sm text-muted">{status.detail}</p>
      </div>

      {result.signal_quality.issues.length > 0 && (
        <ul aria-label="Signal quality" className="flex flex-col gap-2">
          {result.signal_quality.issues.map((issue) => (
            <li key={issue.code} className="rounded-lg border border-warn/40 bg-warn/5 px-4 py-3 text-sm">
              <span className="font-semibold text-warn">{issue.level === 'blocking' ? 'Recording not usable' : 'Quality warning'}.</span>{' '}
              <span className="text-muted">{issue.message}</span>
            </li>
          ))}
        </ul>
      )}

      <p className="text-sm text-muted">
        {alignment.status === 'aligned' &&
          `Compared with ${result.reference?.filename ?? 'the reference'} over ${alignment.words_compared} of ${alignment.transcript_word_count} words recognised in both recordings (${alignment.transcript_source === 'user_provided' ? 'your transcript' : 'machine-recognised text'}).`}
        {alignment.status === 'no_reference' && 'No reference recording was supplied, so only the rules that need no reference were run.'}
        {alignment.status === 'unavailable' && `The reference recording was not used. ${alignment.reason}`}
        {alignment.status === 'aligned' &&
          alignment.words_excluded &&
          Object.keys(alignment.words_excluded).length > 0 &&
          ` Left out of the comparison: ${Object.entries(alignment.words_excluded)
            .map(([reason, count]) => `${count} ${reason.replaceAll('_', ' ')}`)
            .join(', ')}.`}
      </p>

      {result.findings.length === 0 ? (
        <EmptyState
          title={result.status === 'partial' ? 'No findings could be established' : 'No supported findings'}
          description={
            result.status === 'partial'
              ? 'Part of the analysis could not run, so an empty list here does not mean the delivery was checked and found fine. See the rules below.'
              : 'Nothing measured crossed a threshold. This does not rate the delivery as good; it means no rule had evidence of a difference.'
          }
        />
      ) : (
        <ol aria-label="Findings" className="flex flex-col gap-3">
          {result.findings.map((finding) => (
            <FindingCard key={finding.id} finding={finding} onSeek={onSeek} />
          ))}
        </ol>
      )}

      <div>
        <h3 className="text-xs font-semibold tracking-widest text-muted uppercase">Rules checked</h3>
        <ul aria-label="Rules checked" className="mt-2 flex flex-col gap-1.5">
          {result.rules.map((rule) => (
            <li key={`${rule.rule_id}-${rule.category}`} className="rounded-lg border border-line bg-ink-900 px-3 py-2 text-sm">
              <span className="font-medium">{categoryLabel[rule.category]}</span>{' '}
              <span className={rule.status === 'triggered' ? 'text-accent' : rule.status === 'not_triggered' ? 'text-muted' : 'text-warn'}>
                · {ruleStatusLabel[rule.status]}
                {rule.status === 'triggered' && ` (${rule.findings})`}
              </span>
              {rule.reason && <span className="mt-0.5 block text-xs text-muted">{rule.reason}</span>}
            </li>
          ))}
        </ul>
      </div>

      <ul className="list-disc space-y-1 pl-5 text-xs text-muted">
        {result.limitations.map((limitation) => (
          <li key={limitation}>{limitation}</li>
        ))}
      </ul>
    </div>
  )
}
