import { AnalysisGate } from '../components/AnalysisGate'
import { DemoOnlyNotice } from '../components/SourceSwitch'
import { btnSecondary, Card, DemoBadge, EvidenceKindBadge, PageHeader, SeverityBadge } from '../components/ui'
import { formatInterval, formatPercent, formatTime } from '../lib/format'
import { severityLabel } from '../lib/theme'
import type { AnalysisResult, Severity } from '../types'

const severities: Severity[] = ['high', 'medium', 'low']

function ReportPreview({ analysis }: { analysis: AnalysisResult }) {
  return (
    <Card as="article" aria-labelledby="report-title" className="mx-auto max-w-4xl">
      <header className="border-b border-line pb-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 id="report-title" className="text-2xl font-semibold">
              Speech delivery report
            </h2>
            <p className="mt-1 font-mono text-xs text-muted">
              {analysis.id} · duration {formatTime(analysis.durationSec)}
            </p>
          </div>
          <DemoBadge />
        </div>
        <p className="mt-3 text-sm text-muted">{analysis.provenance}</p>
      </header>

      <section aria-labelledby="report-summary" className="border-b border-line py-5">
        <h3 id="report-summary" className="text-xs font-semibold tracking-widest text-muted uppercase">
          Summary
        </h3>
        <dl className="mt-3 grid grid-cols-3 gap-3">
          {severities.map((severity) => (
            <div key={severity} className="rounded-lg border border-line bg-ink-900 p-3">
              <dt className="text-xs text-muted">{severityLabel[severity]} severity</dt>
              <dd className="mt-1 font-mono text-xl font-semibold">
                {analysis.findings.filter((f) => f.severity === severity).length}
              </dd>
            </div>
          ))}
        </dl>
      </section>

      <section aria-labelledby="report-findings" className="border-b border-line py-5">
        <h3 id="report-findings" className="text-xs font-semibold tracking-widest text-muted uppercase">
          Findings
        </h3>
        <ol className="mt-3 flex flex-col gap-4">
          {analysis.findings.map((finding, index) => {
            const tips = analysis.coachTips.filter((tip) => tip.findingId === finding.id)
            return (
              <li key={finding.id} className="rounded-lg border border-line bg-ink-900 p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <h4 className="text-base font-semibold">
                    {index + 1}. {finding.title}
                  </h4>
                  <SeverityBadge severity={finding.severity} />
                </div>
                <p className="mt-1 font-mono text-xs text-muted">
                  {formatInterval(finding.interval)} · confidence {formatPercent(finding.confidence)}
                </p>
                <p className="mt-2 text-sm">{finding.summary}</p>
                <ul className="mt-3 flex flex-col gap-1.5 text-sm">
                  {finding.evidence.map((item) => (
                    <li key={`${item.kind}-${item.label}`} className="flex flex-wrap items-baseline gap-2">
                      <EvidenceKindBadge kind={item.kind} />
                      <span className="text-muted">
                        {item.label}
                        {item.participant && `: ${item.participant}`}
                        {item.baseline && ` (baseline ${item.baseline})`}
                        {item.detail && ` — ${item.detail}`}
                      </span>
                    </li>
                  ))}
                </ul>
                {tips.map((tip) => (
                  <p key={tip.id} className="mt-3 border-l-2 border-accent/50 pl-3 text-sm">
                    <span className="text-muted">Recommendation: </span>
                    {tip.action}
                  </p>
                ))}
              </li>
            )
          })}
        </ol>
      </section>

      <section aria-labelledby="report-limitations" className="pt-5">
        <h3 id="report-limitations" className="text-xs font-semibold tracking-widest text-muted uppercase">
          Limitations
        </h3>
        <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-muted">
          {analysis.limitations.map((limitation) => (
            <li key={limitation}>{limitation}</li>
          ))}
        </ul>
      </section>
    </Card>
  )
}

export default function Reports() {
  return (
    <>
      <div className="print:hidden">
        <PageHeader
          eyebrow="Reports"
          title="Report preview"
          description="A shareable summary of the findings, their evidence and the recommended next steps."
        >
          <button type="button" className={btnSecondary} onClick={() => window.print()}>
            Print or save as PDF
          </button>
        </PageHeader>
      </div>
      <div className="print:hidden">
        <DemoOnlyNotice feature="report generation" />
      </div>
      <AnalysisGate>{(analysis) => <ReportPreview analysis={analysis} />}</AnalysisGate>
    </>
  )
}
