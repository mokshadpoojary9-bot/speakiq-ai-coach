// Pure helpers that reshape backend measurements for display. They only resample or convert
// units of values the backend returned; they never fill gaps or create new data.

import type { FrameSeries, PauseInterval } from './api'
import { colors } from './theme'

export interface TimelineMarker {
  id: string
  label: string
  start: number
  end: number
  color: string
}

export interface SeriesPoint {
  t: number
  value: number | null
}

export const PAUSE_COLOR = '#8fb8d8'

export function seriesTime(series: FrameSeries, index: number): number {
  return series.start_sec + index * series.hop_sec
}

/** Keep at most `maxPoints` by taking every n-th value. */
export function thinSeries(series: FrameSeries, maxPoints: number): SeriesPoint[] {
  const stride = Math.max(1, Math.ceil(series.values.length / maxPoints))
  const points: SeriesPoint[] = []
  for (let i = 0; i < series.values.length; i += stride) {
    points.push({ t: Number(seriesTime(series, i).toFixed(3)), value: series.values[i] })
  }
  return points
}

/** Mean of the non-null values falling in each of `count` equal time buckets; null for empty buckets. */
export function bucketMeans(series: FrameSeries, durationSec: number, count: number): (number | null)[] {
  const sums = new Array<number>(count).fill(0)
  const sizes = new Array<number>(count).fill(0)
  series.values.forEach((value, i) => {
    if (value === null) return
    const bucket = Math.floor((seriesTime(series, i) / durationSec) * count)
    if (bucket < 0 || bucket >= count) return
    sums[bucket] += value
    sizes[bucket] += 1
  })
  return sums.map((sum, i) => (sizes[i] ? sum / sizes[i] : null))
}

export function hzToSemitones(hz: number, referenceHz: number): number {
  return 12 * Math.log2(hz / referenceHz)
}

const pauseLabel: Record<PauseInterval['position'], string> = {
  leading: 'Silence before speech',
  internal: 'Pause',
  trailing: 'Silence after speech',
}

export function pauseMarkers(intervals: PauseInterval[]): TimelineMarker[] {
  return intervals.map((interval, i) => ({
    id: `pause-${i}`,
    label: pauseLabel[interval.position],
    start: interval.start,
    end: interval.end,
    color: interval.position === 'internal' ? PAUSE_COLOR : colors.baseline,
  }))
}
