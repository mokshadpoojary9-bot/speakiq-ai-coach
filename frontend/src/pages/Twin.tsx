import { useState } from 'react'
import { AnalysisGate } from '../components/AnalysisGate'
import { AcousticTwin } from '../components/twin/AcousticTwin'
import { Card, DemoBadge, PageHeader } from '../components/ui'
import { formatInterval } from '../lib/format'
import type { AnalysisResult } from '../types'

function TwinContent({ analysis }: { analysis: AnalysisResult }) {
  const [selectedId, setSelectedId] = useState<string | null>(null)

  return (
    <div className="flex flex-col gap-6">
      <Card aria-label="Acoustic Twin visualization">
        <AcousticTwin analysis={analysis} selectedId={selectedId} />
      </Card>

      <Card aria-labelledby="twin-highlight-heading">
        <h2 id="twin-highlight-heading" className="text-lg font-semibold">
          Highlight an interval
        </h2>
        <p className="mt-1 text-sm text-muted">Choose a finding to emphasise its interval in the view above.</p>
        <div className="mt-4 flex flex-wrap gap-2">
          {analysis.findings.map((finding) => {
            const selected = finding.id === selectedId
            return (
              <button
                key={finding.id}
                type="button"
                aria-pressed={selected}
                onClick={() => setSelectedId(selected ? null : finding.id)}
                className={`rounded-lg border px-3 py-2 text-left text-sm transition-colors ${
                  selected ? 'border-accent/60 bg-ink-700' : 'border-line bg-ink-900 hover:border-muted/50'
                }`}
              >
                <span className="block font-medium">{finding.title}</span>
                <span className="block font-mono text-xs text-muted">{formatInterval(finding.interval)}</span>
              </button>
            )
          })}
        </div>
      </Card>

      <Card aria-labelledby="twin-reading-heading">
        <h2 id="twin-reading-heading" className="text-lg font-semibold">
          How to read it
        </h2>
        <ul className="mt-3 list-disc space-y-1.5 pl-5 text-sm text-muted">
          <li>Time runs left to right. Each bar is one analysis frame.</li>
          <li>Bar height is energy relative to that speaker’s own median, so the two speakers are comparable.</li>
          <li>The participant is the front (or top) row and the baseline is the back (or bottom) row.</li>
          <li>In 3D, the lines above each row trace the pitch contour in semitones.</li>
          <li>Coloured bars and shaded bands mark flaw intervals by severity.</li>
        </ul>
        <p className="mt-4 text-sm text-muted">{analysis.provenance}</p>
      </Card>
    </div>
  )
}

export default function Twin() {
  return (
    <>
      <PageHeader
        eyebrow="Acoustic Twin"
        title="Your delivery, side by side with the baseline"
        description="A spatial view of the same frames shown on the dashboard. It displays supplied data only and never simulates live metrics."
      >
        <DemoBadge />
      </PageHeader>
      <AnalysisGate>{(analysis) => <TwinContent analysis={analysis} />}</AnalysisGate>
    </>
  )
}
