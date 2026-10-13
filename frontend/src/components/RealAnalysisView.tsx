import { useState } from 'react'
import type { AudioFeatures, Metric } from '../lib/api'
import { formatTime, validInterval } from '../lib/format'
import { pauseMarkers } from '../lib/measurements'
import type { AnalysisSession } from '../lib/session'
import { AudioPreview } from './AudioPreview'
import { categoryColor, FindingsPanel } from './FindingsPanel'
import { MeasuredCharts } from './MeasuredCharts'
import { TranscriptPanel } from './TranscriptPanel'
import { Card, MetricStatusBadge } from './ui'
import { WaveformTimeline } from './WaveformTimeline'

function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="rounded-xl border border-line bg-ink-800 p-4">
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="mt-1 font-mono text-2xl font-semibold">{value}</dd>
      {note && <dd className="mt-1 text-xs text-muted">{note}</dd>}
    </div>
  )
}

const dash = '—'
const fixed = (value: number | null, digits: number, unit: string) =>
  value === null ? dash : `${value.toFixed(digits)} ${unit}`

function metricRows(features: AudioFeatures): { name: string; metric: Metric }[] {
  return [
    { name: 'Waveform', metric: features.waveform },
    ...(features.clipping ? [{ name: 'Clipping', metric: features.clipping }] : []),
    { name: 'Energy', metric: features.energy },
    { name: 'Spectral features', metric: features.spectral },
    { name: 'MFCCs', metric: features.mfcc },
    { name: 'Pitch (F0)', metric: features.pitch },
    { name: 'Pauses', metric: features.pauses },
    { name: 'Speaking rate', metric: features.speaking_rate },
    { name: 'Words per minute', metric: features.transcript_rate },
  ]
}

/** Recording-quality problems the backend reported. Says nothing when there is nothing to say. */
function QualityNotices({ features }: { features: AudioFeatures }) {
  const notices: { title: string; detail: string }[] = []
  const clipping = features.clipping
  if (clipping?.verdict === 'detected') {
    notices.push({
      title: 'Clipping detected',
      detail: `The recording has ${clipping.flat_top_runs ?? 'several'} flat-topped peaks, so it was recorded too loud and is distorted. Measurements from it are less trustworthy.`,
    })
  } else if (clipping?.verdict === 'uncertain') {
    notices.push({ title: 'Clipping could not be ruled out', detail: clipping.limitations[0] ?? '' })
  }
  if (features.pitch.reliability === 'low') {
    notices.push({ title: 'Pitch tracking is unreliable for this recording', detail: features.pitch.limitations[0] ?? '' })
  }
  if (features.pauses.reliability === 'low') {
    notices.push({ title: 'Pause detection is unreliable for this recording', detail: features.pauses.limitations[0] ?? '' })
  }
  if (notices.length === 0) return null
  return (
    <ul aria-label="Recording quality notices" className="flex flex-col gap-2">
      {notices.map((notice) => (
        <li key={notice.title} className="rounded-lg border border-warn/40 bg-warn/5 px-4 py-3 text-sm">
          <span className="font-semibold text-warn">{notice.title}.</span> <span className="text-muted">{notice.detail}</span>
        </li>
      ))}
    </ul>
  )
}

/** Dashboard body for a real backend analysis. Shows only what the backend returned. */
export function RealAnalysisView({ session }: { session: AnalysisSession }) {
  const { result, file } = session
  const { features } = result
  const [seek, setSeek] = useState<{ time: number; nonce: number } | null>(null)
  const pauses = pauseMarkers(features.pauses.intervals)
  // Only findings whose timestamps are valid for this recording are drawn or offered for playback.
  const findingMarkers = result.findings
    .filter((finding) => validInterval(finding.start, finding.end, features.audio.duration_sec) !== null)
    .map((finding) => ({
      id: finding.id,
      label: finding.title,
      start: finding.start,
      end: finding.end,
      color: categoryColor[finding.category],
    }))
  const play = file ? (time: number) => setSeek((previous) => ({ time, nonce: (previous?.nonce ?? 0) + 1 })) : undefined
  const duration = features.audio.duration_sec

  return (
    <div className="flex flex-col gap-6">
      <QualityNotices features={features} />
      <dl className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Duration" value={formatTime(duration)} note={`${features.audio.sample_rate_hz} Hz, ${features.audio.channels} ch`} />
        <Stat
          label="Median pitch"
          value={fixed(features.pitch.median_hz, 0, 'Hz')}
          note={features.pitch.reliability === 'low' ? 'measured, low reliability' : features.pitch.status}
        />
        <Stat
          label="Pauses within speech"
          value={features.pauses.internal_pause_count === null ? dash : String(features.pauses.internal_pause_count)}
          note={features.pauses.reliability === 'low' ? 'measured, low confidence' : features.pauses.status}
        />
        <Stat
          label="Speaking rate"
          value={fixed(features.speaking_rate.speech_rate_syll_per_sec, 1, 'syll/s')}
          note={features.speaking_rate.status === 'estimated' ? 'estimate, not a count' : features.speaking_rate.status}
        />
      </dl>

      <Card aria-labelledby="recording-heading">
        <h2 id="recording-heading" className="text-lg font-semibold">
          Recording
        </h2>
        <p className="mt-1 mb-4 text-sm text-muted">
          Waveform peaks measured by the backend. Shaded bands are{' '}
          {findingMarkers.length > 0 ? 'the intervals of the findings below' : 'detected silences'}
          {features.pauses.status === 'unavailable' && findingMarkers.length === 0 && ' (unavailable for this recording)'}.
        </p>
        <WaveformTimeline
          peaks={features.waveform.peaks}
          durationSec={duration}
          markers={findingMarkers.length > 0 ? findingMarkers : pauses}
          description={`Measured waveform of ${features.audio.filename}, ${formatTime(duration)} long, with ${
            findingMarkers.length > 0 ? `${findingMarkers.length} finding intervals` : `${pauses.length} detected silences`
          } shaded`}
          onSelect={play && findingMarkers.length > 0 ? (id) => play(findingMarkers.find((m) => m.id === id)?.start ?? 0) : undefined}
        />
        {file && (
          <div className="mt-5">
            <AudioPreview key={`${file.name}-${file.size}-${file.lastModified}`} file={file} seek={seek} />
          </div>
        )}
      </Card>

      <Card aria-labelledby="transcript-result-heading">
        <h2 id="transcript-result-heading" className="mb-4 text-lg font-semibold">
          Transcript and word timing
        </h2>
        <TranscriptPanel result={result} onSeek={play} />
      </Card>

      <Card aria-labelledby="measured-charts-heading">
        <h2 id="measured-charts-heading" className="mb-4 text-lg font-semibold">
          Measured contours
        </h2>
        <MeasuredCharts features={features} markers={pauses} />
      </Card>

      <Card aria-labelledby="real-findings-heading">
        <h2 id="real-findings-heading" className="mb-4 text-lg font-semibold">
          Findings
        </h2>
        <FindingsPanel result={result} onSeek={play} />
      </Card>

      <Card aria-labelledby="methods-heading">
        <h2 id="methods-heading" className="text-lg font-semibold">
          Methods and limitations
        </h2>
        <ul className="mt-4 flex flex-col gap-2">
          {metricRows(features).map(({ name, metric }) => (
            <li key={name} className="rounded-lg border border-line bg-ink-900">
              <details>
                <summary className="flex cursor-pointer flex-wrap items-center gap-2 rounded-lg px-4 py-3 text-sm font-medium">
                  {name}
                  <MetricStatusBadge status={metric.status} />
                </summary>
                <div className="border-t border-line px-4 py-3 text-sm text-muted">
                  <p>{metric.method}</p>
                  {metric.limitations.length > 0 && (
                    <ul className="mt-2 list-disc space-y-1 pl-5">
                      {metric.limitations.map((limitation) => (
                        <li key={limitation}>{limitation}</li>
                      ))}
                    </ul>
                  )}
                </div>
              </details>
            </li>
          ))}
        </ul>
        <ul className="mt-4 list-disc space-y-1 pl-5 text-sm text-muted">
          {[...result.limitations, ...features.limitations].map((limitation) => (
            <li key={limitation}>{limitation}</li>
          ))}
        </ul>
      </Card>
    </div>
  )
}
