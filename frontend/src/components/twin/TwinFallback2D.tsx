import { formatTime } from '../../lib/format'
import { colors, severityColor } from '../../lib/theme'
import { energyToUnit, findingAt, participantColor, type TwinProps } from './twinData'

const VIEW_W = 960
const ROW_H = 110
const GAP = 34
const LABEL_H = 18
const VIEW_H = LABEL_H * 2 + ROW_H * 2 + GAP

/** 2D equivalent of the Acoustic Twin: same data and colours, plus the raw values as a table. */
export function TwinFallback2D({ analysis, selectedId }: TwinProps) {
  const { frames, findings, durationSec } = analysis
  const step = frames.length > 1 ? frames[1].t - frames[0].t : durationSec
  const x = (t: number) => (t / durationSec) * VIEW_W
  const barW = x(step) * 0.72

  const rows = [
    { label: 'Participant', top: LABEL_H, energy: (i: number) => frames[i].participantEnergy, participant: true },
    { label: 'Baseline', top: LABEL_H * 2 + ROW_H + GAP, energy: (i: number) => frames[i].baselineEnergy, participant: false },
  ]

  return (
    <div>
      <svg
        viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
        className="h-auto w-full rounded-lg border border-line bg-ink-900"
        role="img"
        aria-label={`2D Acoustic Twin: relative energy over ${formatTime(durationSec)} for participant and baseline, with ${findings.length} flaw intervals shaded. Values are in the data table below.`}
      >
        {findings.map((finding) => (
          <rect
            key={finding.id}
            x={x(finding.interval.start)}
            y={0}
            width={x(finding.interval.end - finding.interval.start)}
            height={VIEW_H}
            fill={severityColor[finding.severity]}
            opacity={finding.id === selectedId ? 0.3 : 0.1}
          />
        ))}
        {rows.map((row) => (
          <g key={row.label}>
            <text x={8} y={row.top - 5} fill={colors.muted} fontSize={12}>
              {row.label} energy
            </text>
            <line x1={0} x2={VIEW_W} y1={row.top + ROW_H} y2={row.top + ROW_H} stroke={colors.line} />
            {frames.map((frame, i) => {
              const h = energyToUnit(row.energy(i)) * ROW_H
              return (
                <rect
                  key={frame.t}
                  x={x(frame.t) + (x(step) - barW) / 2}
                  y={row.top + ROW_H - h}
                  width={barW}
                  height={h}
                  rx={2}
                  fill={row.participant ? participantColor(findings, frame.t) : colors.baseline}
                />
              )
            })}
          </g>
        ))}
      </svg>

      <details className="mt-4 rounded-lg border border-line bg-ink-900">
        <summary className="cursor-pointer rounded-lg px-4 py-3 text-sm font-medium">
          View the underlying data as a table ({frames.length} frames)
        </summary>
        <div className="max-h-80 overflow-auto border-t border-line">
          <table className="w-full min-w-[560px] text-left text-sm">
            <caption className="sr-only">Acoustic Twin frames: energy, pitch and flaw interval per time step</caption>
            <thead className="sticky top-0 bg-ink-800 text-xs text-muted">
              <tr>
                <th scope="col" className="px-4 py-2 font-medium">Time</th>
                <th scope="col" className="px-4 py-2 font-medium">Participant energy (dB)</th>
                <th scope="col" className="px-4 py-2 font-medium">Baseline energy (dB)</th>
                <th scope="col" className="px-4 py-2 font-medium">Participant pitch (st)</th>
                <th scope="col" className="px-4 py-2 font-medium">Baseline pitch (st)</th>
                <th scope="col" className="px-4 py-2 font-medium">Flaw</th>
              </tr>
            </thead>
            <tbody className="font-mono text-xs">
              {frames.map((frame) => (
                <tr key={frame.t} className="border-t border-line">
                  <th scope="row" className="px-4 py-1.5 font-normal">{formatTime(frame.t)}</th>
                  <td className="px-4 py-1.5">{frame.participantEnergy.toFixed(1)}</td>
                  <td className="px-4 py-1.5">{frame.baselineEnergy.toFixed(1)}</td>
                  <td className="px-4 py-1.5">{frame.participantPitch.toFixed(1)}</td>
                  <td className="px-4 py-1.5">{frame.baselinePitch.toFixed(1)}</td>
                  <td className="px-4 py-1.5 font-sans">{findingAt(findings, frame.t)?.title ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  )
}
