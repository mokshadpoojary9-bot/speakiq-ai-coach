import { useId, useState } from 'react'
import { AnalysisGate } from '../components/AnalysisGate'
import { FindingDetail, FindingList } from '../components/Findings'
import { RealCoach } from '../components/RealCoach'
import { SourceSwitch, useSource } from '../components/SourceSwitch'
import { Badge, Card, DemoBadge, EmptyState, LiveBadge, PageHeader } from '../components/ui'
import type { AnalysisResult } from '../types'

function CoachContent({ analysis }: { analysis: AnalysisResult }) {
  const questionId = useId()
  const [selectedId, setSelectedId] = useState<string | null>(analysis.findings[0]?.id ?? null)
  const finding = analysis.findings.find((f) => f.id === selectedId) ?? null
  const tips = analysis.coachTips.filter((tip) => tip.findingId === selectedId)

  return (
    <div className="grid gap-6 lg:grid-cols-5">
      <Card className="lg:col-span-2" aria-labelledby="coach-findings-heading">
        <h2 id="coach-findings-heading" className="mb-4 text-lg font-semibold">
          Choose a finding
        </h2>
        <FindingList findings={analysis.findings} selectedId={selectedId} onSelect={setSelectedId} />
      </Card>

      <div className="flex flex-col gap-6 lg:col-span-3">
        <Card aria-labelledby="coach-advice-heading">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 id="coach-advice-heading" className="text-lg font-semibold">
              Coaching
            </h2>
            <Badge>Rule-based · no language model</Badge>
          </div>

          {tips.length === 0 ? (
            <div className="mt-4">
              <EmptyState
                title="No coaching for this selection"
                description="Coaching is only offered where a finding has supporting evidence."
              />
            </div>
          ) : (
            <ul className="mt-4 flex flex-col gap-4">
              {tips.map((tip) => (
                <li key={tip.id} className="animate-rise rounded-lg border border-accent/30 bg-accent/5 p-4">
                  <p className="text-base font-semibold">{tip.action}</p>
                  <p className="mt-3 text-xs font-semibold tracking-widest text-muted uppercase">Try this</p>
                  <p className="mt-1 text-sm text-fg">{tip.drill}</p>
                  <p className="mt-3 text-xs font-semibold tracking-widest text-muted uppercase">Why you’re seeing this</p>
                  <p className="mt-1 text-sm text-muted">{tip.rationale}</p>
                </li>
              ))}
            </ul>
          )}
        </Card>

        {finding && (
          <Card aria-label="Evidence behind this coaching">
            <FindingDetail finding={finding} />
          </Card>
        )}

        <Card aria-labelledby="coach-ask-heading">
          <h2 id="coach-ask-heading" className="text-lg font-semibold">
            Ask a follow-up
          </h2>
          <label htmlFor={questionId} className="mt-3 block text-sm text-muted">
            Your question
          </label>
          <input
            id={questionId}
            type="text"
            disabled
            aria-describedby={`${questionId}-note`}
            placeholder="Not available yet"
            className="mt-2 block w-full cursor-not-allowed rounded-lg border border-line bg-ink-900 p-3 text-sm opacity-60"
          />
          <p id={`${questionId}-note`} className="mt-2 text-sm text-muted">
            Free-form questions are not supported: answering them would need a language model, which this app does not
            use. The coaching above is fixed sample text.
          </p>
        </Card>
      </div>
    </div>
  )
}

export default function Coach() {
  const { source, session, setSource } = useSource()
  const live = source === 'live' && session !== null

  return (
    <>
      <PageHeader
        eyebrow="Evidence Coach"
        title="Advice you can trace back"
        description="Each suggestion names the finding that triggered it and shows the measurements behind it."
      >
        {live ? <LiveBadge filename={session.result.features.audio.filename} /> : <DemoBadge />}
      </PageHeader>
      <SourceSwitch source={source} hasSession={session !== null} onChange={setSource} />
      {live ? <RealCoach session={session} /> : <AnalysisGate>{(analysis) => <CoachContent analysis={analysis} />}</AnalysisGate>}
    </>
  )
}
