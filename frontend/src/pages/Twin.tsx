import { useState } from 'react'
import { AnalysisGate } from '../components/AnalysisGate'
import { SourceSwitch, useSource } from '../components/SourceSwitch'
import { AcousticTwin } from '../components/twin/AcousticTwin'
import { twinFromDemo, twinFromFeatures, type TwinData } from '../components/twin/twinData'
import { Card, DemoBadge, EmptyState, LiveBadge, PageHeader } from '../components/ui'
import { formatInterval } from '../lib/format'

function TwinContent({ data, provenance }: { data: TwinData; provenance: string }) {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const live = data.source === 'live'

  return (
    <div className="flex flex-col gap-6">
      <Card aria-label="Acoustic Twin visualization">
        <AcousticTwin data={data} selectedId={selectedId} />
      </Card>

      <Card aria-labelledby="twin-highlight-heading">
        <h2 id="twin-highlight-heading" className="text-lg font-semibold">
          Highlight an interval
        </h2>
        {data.intervals.length === 0 ? (
          <div className="mt-4">
            <EmptyState
              title="No intervals to highlight"
              description={live ? 'No silences were detected in this recording.' : 'This data has no marked intervals.'}
            />
          </div>
        ) : (
          <>
            <p className="mt-1 text-sm text-muted">
              Choose {live ? 'a detected silence' : 'a finding'} to emphasise its interval in the view above.
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              {data.intervals.map((interval) => {
                const selected = interval.id === selectedId
                return (
                  <button
                    key={interval.id}
                    type="button"
                    aria-pressed={selected}
                    onClick={() => setSelectedId(selected ? null : interval.id)}
                    className={`rounded-lg border px-3 py-2 text-left text-sm transition-colors ${
                      selected ? 'border-accent/60 bg-ink-700' : 'border-line bg-ink-900 hover:border-muted/50'
                    }`}
                  >
                    <span className="block font-medium">{interval.label}</span>
                    <span className="block font-mono text-xs text-muted">{formatInterval(interval)}</span>
                  </button>
                )
              })}
            </div>
          </>
        )}
      </Card>

      <Card aria-labelledby="twin-reading-heading">
        <h2 id="twin-reading-heading" className="text-lg font-semibold">
          How to read it
        </h2>
        <ul className="mt-3 list-disc space-y-1.5 pl-5 text-sm text-muted">
          <li>Time runs left to right. Each bar is one time step.</li>
          {live ? (
            <>
              <li>Bar height is measured frame energy, averaged within each time step and scaled to this recording’s loudest frame.</li>
              <li>In 3D, the line above the bars traces measured pitch in semitones from this speaker’s median, with gaps where speech is unvoiced. The line is drawn within one octave either side; the 2D data table has the exact values.</li>
              <li>Coloured bars and shaded bands are detected silences. They are not flaws.</li>
              <li>There is no baseline row: baseline comparison and flaw detection are not implemented yet.</li>
            </>
          ) : (
            <>
              <li>Bar height is energy relative to that speaker’s own median, so the two speakers are comparable.</li>
              <li>The participant is the front (or top) row and the baseline is the back (or bottom) row.</li>
              <li>In 3D, the lines above each row trace the pitch contour in semitones.</li>
              <li>Coloured bars and shaded bands mark demo flaw intervals by severity.</li>
            </>
          )}
        </ul>
        <p className="mt-4 text-sm text-muted">{provenance}</p>
      </Card>
    </div>
  )
}

export default function Twin() {
  const { source, session, setSource } = useSource()
  const live = source === 'live' && session !== null
  const liveData = live ? twinFromFeatures(session.result.features) : null

  return (
    <>
      <PageHeader
        eyebrow="Acoustic Twin"
        title={live ? 'Your delivery in space' : 'Your delivery, side by side with the baseline'}
        description="A spatial view of the same frames shown on the dashboard. It displays supplied data only and never simulates live metrics."
      >
        {live ? <LiveBadge filename={session.result.features.audio.filename} /> : <DemoBadge />}
      </PageHeader>
      <SourceSwitch source={source} hasSession={session !== null} onChange={setSource} />
      {live ? (
        liveData ? (
          <TwinContent
            key="live"
            data={liveData}
            provenance={`Measured by the backend from ${session.result.features.audio.filename}.`}
          />
        ) : (
          <EmptyState
            title="Nothing to draw for this recording"
            description="The backend did not return an energy contour, so the Acoustic Twin cannot be shown. Switch to the demo fixture to see how it looks."
          />
        )
      ) : (
        <AnalysisGate>
          {(analysis) => <TwinContent key="demo" data={twinFromDemo(analysis)} provenance={analysis.provenance} />}
        </AnalysisGate>
      )}
    </>
  )
}
