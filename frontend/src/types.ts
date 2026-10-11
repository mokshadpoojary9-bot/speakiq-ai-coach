// Frontend data contract. All times are in seconds.

export type Severity = 'high' | 'medium' | 'low'
export type FlawType = 'pace' | 'pause' | 'monotone' | 'energy'

/** measured: computed from audio. inferred: an interpretation. unavailable: could not be checked. */
export type EvidenceKind = 'measured' | 'inferred' | 'unavailable'

export interface Interval {
  start: number
  end: number
}

export interface EvidenceItem {
  kind: EvidenceKind
  label: string
  participant?: string
  baseline?: string
  detail?: string
}

export interface Finding {
  id: string
  type: FlawType
  title: string
  interval: Interval
  severity: Severity
  /** 0 to 1 */
  confidence: number
  summary: string
  transcriptExcerpt: string
  evidence: EvidenceItem[]
  limitations: string[]
}

/** One analysis frame comparing the participant with the baseline delivery. */
export interface FeatureFrame {
  t: number
  /** Semitones relative to each speaker's own median pitch. */
  baselinePitch: number
  participantPitch: number
  /** dB relative to each speaker's own median energy. */
  baselineEnergy: number
  participantEnergy: number
  /** Syllables per second. */
  baselineRate: number
  participantRate: number
}

export interface CoachTip {
  id: string
  findingId: string
  action: string
  drill: string
  rationale: string
  source: 'rule-based'
}

export interface AnalysisResult {
  id: string
  /** True for bundled sample data that was not computed from a real recording. */
  isDemo: boolean
  label: string
  provenance: string
  durationSec: number
  transcript: string
  /** Normalised waveform peaks, 0 to 1, evenly spaced over the duration. */
  peaks: number[]
  frames: FeatureFrame[]
  findings: Finding[]
  coachTips: CoachTip[]
  limitations: string[]
}
