import { colors, severityColor } from '../../lib/theme'
import type { AnalysisResult, Finding } from '../../types'

// Shared by the 3D scene and the 2D fallback so both show the same encoding of the same data.

const ENERGY_FLOOR_DB = -14
const ENERGY_CEIL_DB = 4

/** Maps relative energy in dB to a 0..1 bar height. */
export function energyToUnit(db: number): number {
  const unit = (db - ENERGY_FLOOR_DB) / (ENERGY_CEIL_DB - ENERGY_FLOOR_DB)
  return Math.min(1, Math.max(0.03, unit))
}

export function findingAt(findings: Finding[], t: number): Finding | undefined {
  return findings.find((f) => t >= f.interval.start && t < f.interval.end)
}

export function participantColor(findings: Finding[], t: number): string {
  const finding = findingAt(findings, t)
  return finding ? severityColor[finding.severity] : colors.accent
}

export const twinLegend = [
  { color: colors.accent, label: 'Participant energy' },
  { color: colors.baseline, label: 'Baseline energy' },
  { color: severityColor.high, label: 'High-severity interval' },
  { color: severityColor.medium, label: 'Medium-severity interval' },
  { color: severityColor.low, label: 'Low-severity interval' },
]

export type TwinProps = { analysis: AnalysisResult; selectedId: string | null }
