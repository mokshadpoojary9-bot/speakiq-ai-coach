import { useState } from 'react'
import { AnalysisGate } from '../components/AnalysisGate'
import { FeatureCharts } from '../components/FeatureCharts'
import { FindingDetail, FindingList } from '../components/Findings'
import { RealAnalysisView } from '../components/RealAnalysisView'
import { SourceSwitch, useSource } from '../components/SourceSwitch'
import { Card, DemoBadge, EmptyState, LiveBadge, PageHeader } from '../components/ui'
import { WaveformTimeline } from '../components/WaveformTimeline'
import { formatPercent, formatTime } from '../lib/format'
import { severityColor, severityLabel } from '../lib/theme'
import type { AnalysisResult, Severity } from '../types'

type Filter = 'all' | Severity
const filters: Filter[] = ['all', 'high', 'medium', 'low']

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-line bg-ink-800 p-4">
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="mt-1 font-mono text-2xl font-semibold">{value}</dd>
    </div>
  )
}

function DashboardContent({ analysis }: { analysis: AnalysisResult }) {
  const [filter, setFilter] = useState<Filter>('all')
  const [selectedId, setSelectedId] = useState<string | null>(analysis.findings[0]?.id ?? null)

  const visible = analysis.findings.filter((f) => filter === 'all' || f.severity === filter)
  const selected = visible.find((f) => f.id === selectedId) ?? null
  const flaggedSec = analysis.findings.reduce((sum, f) => sum + (f.interval.end - f.interval.start), 0)

  return (
    <div className="flex flex-col gap-6">
      <dl className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Duration" value={formatTime(analysis.durationSec)} />
        <Stat label="Findings" value={String(analysis.findings.length)} />
        <Stat label="Time flagged" value={formatPercent(flaggedSec / analysis.durationSec)} />
        <Stat label="Frames compared" value={String(analysis.frames.length)} />
      </dl>

      <Card aria-labelledby="timeline-heading">
        <h2 id="timeline-heading" className="text-lg font-semibold">
          Waveform and flaw timeline
        </h2>
        <p className="mt-1 mb-4 text-sm text-muted">
          Select a shaded interval to inspect it. The demo fixture has no audio; analyse your own recording in the
          workspace to get playback and real measurements.
        </p>
        <WaveformTimeline
          peaks={analysis.peaks}
          durationSec={analysis.durationSec}
          markers={visible.map((f) => ({
            id: f.id,
            label: f.title,
            start: f.interval.start,
            end: f.interval.end,
            color: severityColor[f.severity],
          }))}
          description={`Demo waveform of the ${formatTime(analysis.durationSec)} sample with ${visible.length} highlighted demo flaw intervals`}
          selectedId={selected?.id ?? null}
          onSelect={setSelectedId}
        />
      </Card>

      <div className="grid gap-6 lg:grid-cols-5">
        <Card className="lg:col-span-2" aria-labelledby="findings-heading">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <h2 id="findings-heading" className="text-lg font-semibold">
              Findings
            </h2>
            <div role="group" aria-label="Filter by severity" className="inline-flex rounded-lg border border-line bg-ink-900 p-1">
              {filters.map((option) => (
                <button
                  key={option}
                  type="button"
                  aria-pressed={filter === option}
                  onClick={() => setFilter(option)}
                  className={`rounded-md px-2.5 py-1 text-xs transition-colors ${
                    filter === option ? 'bg-ink-700 text-accent' : 'text-muted hover:text-fg'
                  }`}
                >
                  {option === 'all' ? 'All' : severityLabel[option]}
                </button>
              ))}
            </div>
          </div>
          <FindingList findings={visible} selectedId={selected?.id ?? null} onSelect={setSelectedId} />
        </Card>

        <Card className="lg:col-span-3" aria-label="Selected finding">
          {selected ? (
            <FindingDetail finding={selected} />
          ) : (
            <EmptyState title="No finding selected" description="Choose a finding from the list or the timeline." />
          )}
        </Card>
      </div>

      <Card aria-labelledby="charts-heading">
        <h2 id="charts-heading" className="mb-4 text-lg font-semibold">
          Baseline versus participant
        </h2>
        <FeatureCharts frames={analysis.frames} findings={visible} selectedId={selected?.id ?? null} />
      </Card>
    </div>
  )
}

export default function Dashboard() {
  const { source, session, setSource } = useSource()
  const live = source === 'live' && session !== null

  return (
    <>
      <PageHeader
        eyebrow="Dashboard"
        title="Analysis"
        description={
          live
            ? 'Measurements, transcript and word timing returned by the backend for your recording.'
            : 'Where delivery departs from the baseline, when it happens, and the evidence for each finding.'
        }
      >
        {live ? <LiveBadge filename={session.result.features.audio.filename} /> : <DemoBadge />}
      </PageHeader>
      <SourceSwitch source={source} hasSession={session !== null} onChange={setSource} />
      {live ? (
        <RealAnalysisView session={session} />
      ) : (
        <AnalysisGate>{(analysis) => <DashboardContent analysis={analysis} />}</AnalysisGate>
      )}
    </>
  )
}
