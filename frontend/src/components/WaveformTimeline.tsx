import { formatInterval, formatTime } from '../lib/format'
import type { TimelineMarker } from '../lib/measurements'
import { colors } from '../lib/theme'

const VIEW_W = 1000
const VIEW_H = 120

/** Static waveform drawn from supplied peaks, with labelled intervals on top. */
export function WaveformTimeline({
  peaks,
  durationSec,
  markers,
  description,
  selectedId = null,
  onSelect,
}: {
  peaks: number[]
  durationSec: number
  markers: TimelineMarker[]
  /** Accessible summary of what the picture shows. */
  description: string
  selectedId?: string | null
  /** When given, markers are buttons. */
  onSelect?: (id: string) => void
}) {
  const barW = VIEW_W / Math.max(1, peaks.length)
  const tickStep = durationSec <= 30 ? 4 : durationSec <= 120 ? 15 : 60
  const ticks = Array.from({ length: Math.floor(durationSec / tickStep) + 1 }, (_, i) => i * tickStep)

  return (
    <div>
      <div className="relative h-28 overflow-hidden rounded-lg border border-line bg-ink-900 sm:h-32">
        <svg
          viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
          preserveAspectRatio="none"
          className="absolute inset-0 h-full w-full"
          role="img"
          aria-label={description}
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

        {markers.map((marker) => {
          const selected = marker.id === selectedId
          const name = `${marker.label}, ${formatInterval(marker)}`
          const style = {
            left: `${(marker.start / durationSec) * 100}%`,
            width: `${((marker.end - marker.start) / durationSec) * 100}%`,
            borderColor: marker.color,
            backgroundColor: `${marker.color}${selected ? '55' : '26'}`,
          }
          return onSelect ? (
            <button
              key={marker.id}
              type="button"
              onClick={() => onSelect(marker.id)}
              aria-pressed={selected}
              aria-label={name}
              title={name}
              className="absolute inset-y-0 cursor-pointer border-x-2 transition-colors"
              style={style}
            />
          ) : (
            <div key={marker.id} title={name} className="absolute inset-y-0 border-x-2" style={style} />
          )
        })}
      </div>

      <div className="relative mt-1.5 h-4 font-mono text-[11px] text-muted" aria-hidden="true">
        {ticks.map((t) => (
          <span
            key={t}
            className="absolute"
            style={{
              left: `${(t / durationSec) * 100}%`,
              transform: t === 0 ? undefined : t >= durationSec ? 'translateX(-100%)' : 'translateX(-50%)',
            }}
          >
            {formatTime(t)}
          </span>
        ))}
      </div>
    </div>
  )
}
