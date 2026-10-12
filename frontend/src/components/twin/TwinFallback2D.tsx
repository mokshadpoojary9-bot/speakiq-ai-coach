import { formatTime } from '../../lib/format'
import { colors } from '../../lib/theme'
import { barColor, intervalAt, type TwinFrame, type TwinProps } from './twinData'

const VIEW_W = 960
const ROW_H = 110
const GAP = 34
const LABEL_H = 18

const cell = (value: number | null | undefined) => (value === null || value === undefined ? '—' : value.toFixed(1))

/** 2D equivalent of the Acoustic Twin: same data and colours, plus the values as a table. */
export function TwinFallback2D({ data, selectedId }: TwinProps) {
  const { frames, intervals, durationSec, stepSec, hasBaseline, energyUnitLabel } = data
  const x = (t: number) => (t / durationSec) * VIEW_W
  const barW = x(stepSec) * 0.72
  const viewH = hasBaseline ? LABEL_H * 2 + ROW_H * 2 + GAP : LABEL_H + ROW_H + 8

  const rows: { label: string; top: number; unit: (f: TwinFrame) => number | null | undefined; color: (f: TwinFrame) => string }[] = [
    {
      label: hasBaseline ? 'Participant energy' : 'Measured energy',
      top: LABEL_H,
      unit: (f) => f.energyUnit,
      color: (f) => barColor(data, f.t),
    },
  ]
  if (hasBaseline) {
    rows.push({
      label: 'Baseline energy',
      top: LABEL_H * 2 + ROW_H + GAP,
      unit: (f) => f.baselineEnergyUnit,
      color: () => colors.baseline,
    })
  }

  return (
    <div>
      <svg
        viewBox={`0 0 ${VIEW_W} ${viewH}`}
        className="h-auto w-full rounded-lg border border-line bg-ink-900"
        role="img"
        aria-label={`2D Acoustic Twin over ${formatTime(durationSec)}. ${data.summary} Values are in the data table below.`}
      >
        {intervals.map((interval) => (
          <rect
            key={interval.id}
            x={x(interval.start)}
            y={0}
            width={x(interval.end - interval.start)}
            height={viewH}
            fill={interval.color}
            opacity={interval.id === selectedId ? 0.3 : 0.1}
          />
        ))}
        {rows.map((row) => (
          <g key={row.label}>
            <text x={8} y={row.top - 5} fill={colors.muted} fontSize={12}>
              {row.label}
            </text>
            <line x1={0} x2={VIEW_W} y1={row.top + ROW_H} y2={row.top + ROW_H} stroke={colors.line} />
            {frames.map((frame) => {
              const unit = row.unit(frame)
              if (unit === null || unit === undefined) return null
              const h = unit * ROW_H
              return (
                <rect
                  key={frame.t}
                  x={x(frame.t) + (x(stepSec) - barW) / 2}
                  y={row.top + ROW_H - h}
                  width={barW}
                  height={h}
                  rx={2}
                  fill={row.color(frame)}
                />
              )
            })}
          </g>
        ))}
      </svg>

      <details className="mt-4 rounded-lg border border-line bg-ink-900">
        <summary className="cursor-pointer rounded-lg px-4 py-3 text-sm font-medium">
          View the underlying data as a table ({frames.length} time steps)
        </summary>
        <div className="max-h-80 overflow-auto border-t border-line">
          <table className="w-full min-w-[480px] text-left text-sm">
            <caption className="sr-only">Acoustic Twin data: energy, pitch and interval per time step</caption>
            <thead className="sticky top-0 bg-ink-800 text-xs text-muted">
              <tr>
                <th scope="col" className="px-4 py-2 font-medium">Time</th>
                <th scope="col" className="px-4 py-2 font-medium">{hasBaseline ? 'Participant energy' : 'Energy'} ({energyUnitLabel})</th>
                {hasBaseline && <th scope="col" className="px-4 py-2 font-medium">Baseline energy ({energyUnitLabel})</th>}
                <th scope="col" className="px-4 py-2 font-medium">{hasBaseline ? 'Participant pitch' : 'Pitch'} (semitones from median)</th>
                {hasBaseline && <th scope="col" className="px-4 py-2 font-medium">Baseline pitch (semitones from median)</th>}
                <th scope="col" className="px-4 py-2 font-medium">Interval</th>
              </tr>
            </thead>
            <tbody className="font-mono text-xs">
              {frames.map((frame) => (
                <tr key={frame.t} className="border-t border-line">
                  <th scope="row" className="px-4 py-1.5 font-normal">{formatTime(frame.t)}</th>
                  <td className="px-4 py-1.5">{cell(frame.energy)}</td>
                  {hasBaseline && <td className="px-4 py-1.5">{cell(frame.baselineEnergy)}</td>}
                  <td className="px-4 py-1.5">{cell(frame.pitch)}</td>
                  {hasBaseline && <td className="px-4 py-1.5">{cell(frame.baselinePitch)}</td>}
                  <td className="px-4 py-1.5 font-sans">{intervalAt(intervals, frame.t)?.label ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  )
}
