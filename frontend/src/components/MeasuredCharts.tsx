import { CartesianGrid, Line, LineChart, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { AudioFeatures, FrameSeries, MetricStatus } from '../lib/api'
import { thinSeries, type TimelineMarker } from '../lib/measurements'
import { colors } from '../lib/theme'
import { EmptyState, MetricStatusBadge } from './ui'

const MAX_CHART_POINTS = 600

interface ChartSpec {
  title: string
  status: MetricStatus
  series: FrameSeries | null
  note: string
  unavailable: string
}

/** Line charts of the contours the backend measured for one recording. There is no baseline to compare with. */
export function MeasuredCharts({ features, markers }: { features: AudioFeatures; markers: TimelineMarker[] }) {
  const duration = features.audio.duration_sec
  const charts: ChartSpec[] = [
    {
      title: 'Pitch (F0)',
      status: features.pitch.status,
      series: features.pitch.series,
      note: 'Gaps are unvoiced or silent frames.',
      unavailable: features.pitch.limitations[0] ?? 'Pitch was not computed.',
    },
    {
      title: 'Energy',
      status: features.energy.status,
      series: features.energy.series,
      note: 'Frame RMS level; depends on recording gain.',
      unavailable: 'Energy was not computed.',
    },
    {
      title: 'Spectral centroid',
      status: features.spectral.status,
      series: features.spectral.centroid,
      note: 'Shown for non-silent frames.',
      unavailable: 'Spectral features were not computed.',
    },
  ]

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      {charts.map((chart) => (
        <figure key={chart.title} className="rounded-lg border border-line bg-ink-900 p-4">
          <figcaption className="mb-3">
            <span className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-semibold">{chart.title}</span>
              {chart.series && <span className="font-mono text-xs text-muted">{chart.series.unit}</span>}
              <MetricStatusBadge status={chart.status} />
            </span>
            <span className="mt-1 block text-xs text-muted">{chart.note}</span>
          </figcaption>
          {chart.series && chart.series.values.some((v) => v !== null) ? (
            <div className="h-44" role="img" aria-label={`${chart.title} over time for this recording`}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={thinSeries(chart.series, MAX_CHART_POINTS)} margin={{ top: 4, right: 8, bottom: 0, left: -8 }}>
                  <CartesianGrid stroke={colors.line} strokeDasharray="2 4" vertical={false} />
                  <XAxis
                    dataKey="t"
                    type="number"
                    domain={[0, duration]}
                    tickCount={6}
                    stroke={colors.muted}
                    tick={{ fontSize: 11 }}
                    unit="s"
                  />
                  <YAxis stroke={colors.muted} tick={{ fontSize: 11 }} domain={['auto', 'auto']} />
                  <Tooltip
                    contentStyle={{ background: colors.ink800, border: `1px solid ${colors.line}`, borderRadius: 8, fontSize: 12 }}
                    labelFormatter={(t) => `${t}s`}
                  />
                  {markers.map((marker) => (
                    <ReferenceArea
                      key={marker.id}
                      x1={marker.start}
                      x2={marker.end}
                      fill={marker.color}
                      fillOpacity={0.12}
                      strokeOpacity={0}
                    />
                  ))}
                  <Line
                    name={chart.title}
                    dataKey="value"
                    stroke={colors.accent}
                    dot={false}
                    strokeWidth={1.5}
                    connectNulls={false}
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <EmptyState title="Nothing to plot" description={chart.unavailable} />
          )}
        </figure>
      ))}
      <p className="text-xs text-muted lg:col-span-3">
        Shaded bands are detected silences. These charts show this recording only; there is no baseline line because
        baseline comparison is not implemented.
      </p>
    </div>
  )
}
