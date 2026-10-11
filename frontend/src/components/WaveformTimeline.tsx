import { formatInterval, formatTime } from '../lib/format'
import { colors, severityColor } from '../lib/theme'
import type { Finding } from '../types'

const VIEW_W = 1000
const VIEW_H = 120

/** Static waveform drawn from supplied peaks, with selectable flaw intervals on top. */
export function WaveformTimeline({
  peaks,
  durationSec,
  findings,
  selectedId,
  onSelect,
}: {
  peaks: number[]
  durationSec: number
  findings: Finding[]
  selectedId: string | null
  onSelect: (id: string) => void
}) {
  const barW = VIEW_W / peaks.length
  const ticks = Array.from({ length: Math.floor(durationSec / 4) + 1 }, (_, i) => i * 4)

  return (
    <div>
      <div className="relative h-28 overflow-hidden rounded-lg border border-line bg-ink-900 sm:h-32">
        <svg
          viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
          preserveAspectRatio="none"
          className="absolute inset-0 h-full w-full"
          role="img"
          aria-label={`Waveform of the ${formatTime(durationSec)} sample with ${findings.length} highlighted flaw intervals`}
        >
          {peaks.map((peak, i) => {
            const h = Math.max(1, peak * (VIEW_H - 12))
            return (
              <rect
                key={i}
                x={i * barW + barW * 0.15}
                y={(VIEW_H - h) / 2}
                width={barW * 0.7}
                height={h}
                fill={colors.accent}
                opacity={0.75}
              />
            )
          })}
        </svg>

        {findings.map((finding) => {
          const left = (finding.interval.start / durationSec) * 100
          const width = ((finding.interval.end - finding.interval.start) / durationSec) * 100
          const selected = finding.id === selectedId
          const color = severityColor[finding.severity]
          return (
            <button
              key={finding.id}
              type="button"
              onClick={() => onSelect(finding.id)}
              aria-pressed={selected}
              aria-label={`${finding.title}, ${formatInterval(finding.interval)}`}
              title={`${finding.title} · ${formatInterval(finding.interval)}`}
              className="absolute inset-y-0 cursor-pointer border-x-2 transition-colors"
              style={{
                left: `${left}%`,
                width: `${width}%`,
                borderColor: color,
                backgroundColor: `${color}${selected ? '55' : '26'}`,
              }}
            />
          )
        })}
      </div>

      <div className="relative mt-1.5 h-4 font-mono text-[11px] text-muted" aria-hidden="true">
        {ticks.map((t) => (
          <span
            key={t}
            className="absolute"
            style={{ left: `${(t / durationSec) * 100}%`, transform: t === 0 ? undefined : t >= durationSec ? 'translateX(-100%)' : 'translateX(-50%)' }}
          >
            {formatTime(t)}
          </span>
        ))}
      </div>
    </div>
  )
}
