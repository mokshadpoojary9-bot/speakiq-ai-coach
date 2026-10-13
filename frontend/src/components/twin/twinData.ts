import type { AudioFeatures } from '../../lib/api'
import { bucketMeans, hzToSemitones, pauseMarkers, PAUSE_COLOR, type TimelineMarker } from '../../lib/measurements'
import { colors, severityColor } from '../../lib/theme'
import type { AnalysisResult } from '../../types'

// One neutral shape for the 3D scene and the 2D fallback, so both show the same encoding of the
// same data whether it comes from the demo fixture or from a real backend analysis.

export interface TwinFrame {
  t: number
  /** Bar height, 0 to 1. Null when there is no value for this frame. */
  energyUnit: number | null
  /** The underlying value, for the data table. */
  energy: number | null
  /** Pitch in semitones relative to the speaker's median; null when unvoiced or unknown. */
  pitch: number | null
  baselineEnergyUnit?: number
  baselineEnergy?: number
  baselinePitch?: number
}

export interface TwinData {
  source: 'demo' | 'live'
  durationSec: number
  stepSec: number
  frames: TwinFrame[]
  intervals: TimelineMarker[]
  hasBaseline: boolean
  energyUnitLabel: string
  legend: { color: string; label: string }[]
  /** Plain-language summary used as the accessible description. */
  summary: string
}

export type TwinProps = { data: TwinData; selectedId: string | null }

const DEMO_FLOOR_DB = -14
const DEMO_CEIL_DB = 4
const LIVE_RANGE_DB = 45
const LIVE_BARS = 96

const clampUnit = (unit: number) => Math.min(1, Math.max(0.03, unit))

/** Maps the fixture's relative energy in dB to a 0..1 bar height. */
export function energyToUnit(db: number): number {
  return clampUnit((db - DEMO_FLOOR_DB) / (DEMO_CEIL_DB - DEMO_FLOOR_DB))
}

export function intervalAt(intervals: TimelineMarker[], t: number): TimelineMarker | undefined {
  return intervals.find((interval) => t >= interval.start && t < interval.end)
}

export function barColor(data: TwinData, t: number): string {
  return intervalAt(data.intervals, t)?.color ?? colors.accent
}

export function twinFromDemo(analysis: AnalysisResult): TwinData {
  const { frames, findings, durationSec } = analysis
  return {
    source: 'demo',
    durationSec,
    stepSec: frames.length > 1 ? frames[1].t - frames[0].t : durationSec,
    frames: frames.map((frame) => ({
      t: frame.t,
      energyUnit: energyToUnit(frame.participantEnergy),
      energy: frame.participantEnergy,
      pitch: frame.participantPitch,
      baselineEnergyUnit: energyToUnit(frame.baselineEnergy),
      baselineEnergy: frame.baselineEnergy,
      baselinePitch: frame.baselinePitch,
    })),
    intervals: findings.map((finding) => ({
      id: finding.id,
      label: finding.title,
      start: finding.interval.start,
      end: finding.interval.end,
      color: severityColor[finding.severity],
    })),
    hasBaseline: true,
    energyUnitLabel: 'dB relative to median',
    legend: [
      { color: colors.accent, label: 'Participant energy' },
      { color: colors.baseline, label: 'Baseline energy' },
      { color: severityColor.high, label: 'High-severity interval' },
      { color: severityColor.medium, label: 'Medium-severity interval' },
      { color: severityColor.low, label: 'Low-severity interval' },
    ],
    summary:
      'Demo fixture. Bar height shows relative energy over time; the front row is the participant and the back row is the baseline. Coloured bars mark demo flaw intervals.',
  }
}

/** Returns null when the backend did not return an energy contour to draw. */
export function twinFromFeatures(features: AudioFeatures): TwinData | null {
  const { energy, pitch, pauses, audio } = features
  if (!energy.series || energy.max_db === null || audio.duration_sec <= 0) return null

  const durationSec = audio.duration_sec
  const count = Math.min(LIVE_BARS, energy.series.values.length)
  const stepSec = durationSec / count
  const energyMeans = bucketMeans(energy.series, durationSec, count)
  const pitchMeans = pitch.series ? bucketMeans(pitch.series, durationSec, count) : null
  const floor = energy.max_db - LIVE_RANGE_DB
  const median = pitch.median_hz

  return {
    source: 'live',
    durationSec,
    stepSec,
    frames: energyMeans.map((db, i) => {
      const hz = pitchMeans?.[i] ?? null
      return {
        t: Number((i * stepSec).toFixed(3)),
        energyUnit: db === null ? null : clampUnit((db - floor) / LIVE_RANGE_DB),
        energy: db === null ? null : Number(db.toFixed(1)),
        pitch: hz !== null && median ? Number(hzToSemitones(hz, median).toFixed(2)) : null,
      }
    }),
    intervals: pauseMarkers(pauses.intervals),
    hasBaseline: false,
    energyUnitLabel: 'dBFS',
    legend: [
      { color: colors.accent, label: 'Measured energy' },
      { color: PAUSE_COLOR, label: 'Detected pause' },
      { color: colors.baseline, label: 'Silence before or after speech' },
    ],
    summary: `Measured from ${audio.filename}. Bar height shows frame energy averaged into ${count} time steps; coloured bars are detected silences. Only this recording is drawn; the reference recording, if one was used, is not shown here.`,
  }
}
