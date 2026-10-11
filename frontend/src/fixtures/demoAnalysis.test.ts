import { describe, expect, it } from 'vitest'
import { demoAnalysis } from './demoAnalysis'

describe('demo fixture', () => {
  it('is marked as demo data and says where it came from', () => {
    expect(demoAnalysis.isDemo).toBe(true)
    expect(demoAnalysis.provenance).toMatch(/not computed from any recording/i)
  })

  it('ties every finding to a valid interval inside the recording', () => {
    for (const finding of demoAnalysis.findings) {
      expect(finding.interval.start).toBeGreaterThanOrEqual(0)
      expect(finding.interval.end).toBeGreaterThan(finding.interval.start)
      expect(finding.interval.end).toBeLessThanOrEqual(demoAnalysis.durationSec)
    }
  })

  it('gives every finding measured evidence, limitations and a confidence between 0 and 1', () => {
    for (const finding of demoAnalysis.findings) {
      expect(finding.evidence.some((e) => e.kind === 'measured')).toBe(true)
      expect(finding.limitations.length).toBeGreaterThan(0)
      expect(finding.confidence).toBeGreaterThan(0)
      expect(finding.confidence).toBeLessThanOrEqual(1)
    }
  })

  it('links every coaching tip to an existing finding', () => {
    const ids = new Set(demoAnalysis.findings.map((f) => f.id))
    for (const tip of demoAnalysis.coachTips) {
      expect(ids.has(tip.findingId)).toBe(true)
      expect(tip.source).toBe('rule-based')
    }
  })

  it('has frames in time order inside the duration, with finite values', () => {
    const { frames, durationSec } = demoAnalysis
    expect(frames[0].t).toBe(0)
    expect(frames.at(-1)!.t).toBeLessThan(durationSec)
    frames.forEach((frame, i) => {
      if (i > 0) expect(frame.t).toBeGreaterThan(frames[i - 1].t)
      expect(Object.values(frame).every(Number.isFinite)).toBe(true)
    })
    expect(demoAnalysis.peaks.every((p) => p >= 0 && p <= 1)).toBe(true)
  })

  it('reports evidence values that match the frames they describe', () => {
    const pace = demoAnalysis.findings.find((f) => f.id === 'f-pace')!
    const inInterval = demoAnalysis.frames.filter((f) => f.t >= pace.interval.start && f.t < pace.interval.end)
    const mean = inInterval.reduce((sum, f) => sum + f.participantRate, 0) / inInterval.length

    expect(pace.evidence[0].participant).toBe(`${mean.toFixed(1)} syll/s`)
  })
})
