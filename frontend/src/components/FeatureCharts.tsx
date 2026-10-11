import { CartesianGrid, Line, LineChart, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { colors, severityColor } from '../lib/theme'
import type { FeatureFrame, Finding } from '../types'

interface ChartSpec {
  title: string
  unit: string
  note: string
  baselineKey: keyof FeatureFrame
  participantKey: keyof FeatureFrame
}

const charts: ChartSpec[] = [
  {
    title: 'Pitch',
    unit: 'semitones',
    note: 'Relative to each speaker’s median pitch.',
    baselineKey: 'baselinePitch',
    participantKey: 'participantPitch',
  },
  {
    title: 'Energy',
    unit: 'dB',
    note: 'Relative to each speaker’s median energy.',
    baselineKey: 'baselineEnergy',
    participantKey: 'participantEnergy',
  },
  {
    title: 'Speech rate',
    unit: 'syll/s',
    note: 'Syllables per second.',
    baselineKey: 'baselineRate',
    participantKey: 'participantRate',
  },
]

/** Baseline-versus-participant line charts with flaw intervals shaded. */
export function FeatureCharts({
  frames,
  findings,
  selectedId,
}: {
  frames: FeatureFrame[]
  findings: Finding[]
  selectedId: string | null
}) {
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      {charts.map((chart) => (
        <figure key={chart.title} className="rounded-lg border border-line bg-ink-900 p-4">
          <figcaption className="mb-3">
            <span className="text-sm font-semibold">{chart.title}</span>
            <span className="ml-2 font-mono text-xs text-muted">{chart.unit}</span>
            <span className="mt-0.5 block text-xs text-muted">{chart.note}</span>
          </figcaption>
          <div className="h-44" role="img" aria-label={`${chart.title} over time, participant compared with baseline`}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={frames} margin={{ top: 4, right: 8, bottom: 0, left: -18 }}>
                <CartesianGrid stroke={colors.line} strokeDasharray="2 4" vertical={false} />
                <XAxis
                  dataKey="t"
                  type="number"
                  domain={[0, 'dataMax']}
                  tickCount={7}
                  stroke={colors.muted}
                  tick={{ fontSize: 11 }}
                  unit="s"
                />
                <YAxis stroke={colors.muted} tick={{ fontSize: 11 }} />
                <Tooltip
                  contentStyle={{ background: colors.ink800, border: `1px solid ${colors.line}`, borderRadius: 8, fontSize: 12 }}
                  labelFormatter={(t) => `${t}s`}
                />
                {findings.map((finding) => (
                  <ReferenceArea
                    key={finding.id}
                    x1={finding.interval.start}
                    x2={finding.interval.end}
                    fill={severityColor[finding.severity]}
                    fillOpacity={finding.id === selectedId ? 0.28 : 0.1}
                    strokeOpacity={0}
                  />
                ))}
                <Line
                  name="Baseline"
                  dataKey={chart.baselineKey}
                  stroke={colors.baseline}
                  strokeDasharray="4 3"
                  dot={false}
                  strokeWidth={1.5}
                  isAnimationActive={false}
                />
                <Line
                  name="Participant"
                  dataKey={chart.participantKey}
                  stroke={colors.accent}
                  dot={false}
                  strokeWidth={2}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </figure>
      ))}
      <p className="flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-muted lg:col-span-3">
        <span className="inline-flex items-center gap-2">
          <span aria-hidden="true" className="h-0.5 w-5 bg-accent" /> Participant
        </span>
        <span className="inline-flex items-center gap-2">
          <span aria-hidden="true" className="h-0 w-5 border-t-2 border-dashed border-[#7d8a84]" /> Baseline
        </span>
        <span>Shaded bands mark flaw intervals.</span>
      </p>
    </div>
  )
}
