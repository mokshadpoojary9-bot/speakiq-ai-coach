// DEMO FIXTURE - NOT REAL ANALYSIS.
// Every number here is authored by hand or produced by the deterministic formulas below.
// Nothing was measured from a recording. It exists so the interface can be built and
// reviewed before the analysis backend exists. Keep `isDemo: true` and keep the UI labels.

import type { AnalysisResult, FeatureFrame, Finding, Interval } from '../types'

const DURATION = 24
const FRAME_STEP = 0.5

const PACE: Interval = { start: 4, end: 7.5 }
const PAUSE: Interval = { start: 10, end: 11.5 }
const MONOTONE: Interval = { start: 13, end: 18 }
const FADE: Interval = { start: 20, end: 24 }

const inside = (t: number, i: Interval) => t >= i.start && t < i.end
const round = (n: number, digits = 1) => Number(n.toFixed(digits))

function buildFrames(): FeatureFrame[] {
  const frames: FeatureFrame[] = []
  for (let t = 0; t < DURATION; t += FRAME_STEP) {
    const baselinePitch = 2.9 * Math.sin(t * 0.9)
    const baselineEnergy = 1.5 * Math.sin(t * 0.6 + 1)
    const baselineRate = 4.3 + 0.3 * Math.sin(t * 0.4)

    let participantPitch = 2.6 * Math.sin(t * 0.9 + 0.2)
    let participantEnergy = 1.4 * Math.sin(t * 0.6 + 0.8)
    let participantRate = 4.4 + 0.3 * Math.sin(t * 0.4 + 0.3)

    if (inside(t, PACE)) participantRate = 6.4 + 0.2 * Math.sin(t * 2)
    if (inside(t, PAUSE)) {
      participantRate = 0
      participantEnergy = -12
      participantPitch = 0
    }
    if (inside(t, MONOTONE)) participantPitch = 0.5 * Math.sin(t * 0.9 + 0.2)
    if (inside(t, FADE)) participantEnergy = -5 - 1.5 * (t - FADE.start)

    frames.push({
      t: round(t),
      baselinePitch: round(baselinePitch),
      participantPitch: round(participantPitch),
      baselineEnergy: round(baselineEnergy),
      participantEnergy: round(participantEnergy),
      baselineRate: round(baselineRate),
      participantRate: round(participantRate),
    })
  }
  return frames
}

function buildPeaks(count: number): number[] {
  return Array.from({ length: count }, (_, i) => {
    const t = (i / count) * DURATION
    if (inside(t, PAUSE)) return 0.02
    const envelope = 0.55 + 0.25 * Math.sin(t * 1.7) + 0.15 * Math.sin(t * 7.3 + 1)
    const fade = inside(t, FADE) ? 1 - 0.2 * (t - FADE.start) : 1
    return round(Math.min(1, Math.max(0.04, Math.abs(envelope) * fade)), 3)
  })
}

const frames = buildFrames()

type NumericKey = Exclude<keyof FeatureFrame, 't'>
const values = (key: NumericKey, i: Interval) => frames.filter((f) => inside(f.t, i)).map((f) => f[key])
const mean = (key: NumericKey, i: Interval) => {
  const v = values(key, i)
  return v.reduce((a, b) => a + b, 0) / v.length
}
const range = (key: NumericKey, i: Interval) => {
  const v = values(key, i)
  return Math.max(...v) - Math.min(...v)
}
const fmt = (n: number, unit: string) => `${n.toFixed(1)} ${unit}`

const NO_ALIGNMENT = 'Word-level forced alignment is not part of the demo fixture, so the transcript excerpt is approximate.'

const findings: Finding[] = [
  {
    id: 'f-pace',
    type: 'pace',
    title: 'Rushed delivery',
    interval: PACE,
    severity: 'high',
    confidence: 0.86,
    summary: 'Speech rate rises well above the baseline for the same sentence.',
    transcriptExcerpt: '“…and that is why the second quarter matters more than any other…”',
    evidence: [
      {
        kind: 'measured',
        label: 'Mean speech rate',
        participant: fmt(mean('participantRate', PACE), 'syll/s'),
        baseline: fmt(mean('baselineRate', PACE), 'syll/s'),
      },
      {
        kind: 'inferred',
        label: 'Likely effect',
        detail: 'Listeners may struggle to follow the key claim. This is an interpretation, not a measurement.',
      },
      { kind: 'unavailable', label: 'Word timestamps', detail: NO_ALIGNMENT },
    ],
    limitations: ['Syllable rate is an estimate and is sensitive to background noise.'],
  },
  {
    id: 'f-pause',
    type: 'pause',
    title: 'Long hesitation pause',
    interval: PAUSE,
    severity: 'medium',
    confidence: 0.78,
    summary: 'A silent gap mid-sentence where the baseline keeps speaking.',
    transcriptExcerpt: '“…because the, [pause] the results were not what we expected…”',
    evidence: [
      {
        kind: 'measured',
        label: 'Silence duration',
        participant: fmt(PAUSE.end - PAUSE.start, 's'),
        baseline: 'no pause in this interval',
      },
      {
        kind: 'measured',
        label: 'Mean energy',
        participant: fmt(mean('participantEnergy', PAUSE), 'dB'),
        baseline: fmt(mean('baselineEnergy', PAUSE), 'dB'),
      },
      {
        kind: 'inferred',
        label: 'Likely cause',
        detail: 'Reads as hesitation rather than a deliberate rhetorical pause, because it falls mid-phrase.',
      },
    ],
    limitations: ['A pause can be intentional. Position within the phrase is the only signal used here.'],
  },
  {
    id: 'f-monotone',
    type: 'monotone',
    title: 'Flat pitch',
    interval: MONOTONE,
    severity: 'medium',
    confidence: 0.71,
    summary: 'Pitch varies far less than the baseline across the same words.',
    transcriptExcerpt: '“…we tested three approaches, compared them, and chose the simplest one…”',
    evidence: [
      {
        kind: 'measured',
        label: 'Pitch range',
        participant: fmt(range('participantPitch', MONOTONE), 'semitones'),
        baseline: fmt(range('baselinePitch', MONOTONE), 'semitones'),
      },
      { kind: 'unavailable', label: 'Word timestamps', detail: NO_ALIGNMENT },
    ],
    limitations: [
      'Pitch is normalised to each speaker’s median; speakers with naturally narrow ranges may be over-flagged.',
    ],
  },
  {
    id: 'f-energy',
    type: 'energy',
    title: 'Trailing energy drop',
    interval: FADE,
    severity: 'low',
    confidence: 0.48,
    summary: 'Loudness falls away through the closing sentence.',
    transcriptExcerpt: '“…and that is what I would recommend going forward.”',
    evidence: [
      {
        kind: 'measured',
        label: 'Mean energy',
        participant: fmt(mean('participantEnergy', FADE), 'dB'),
        baseline: fmt(mean('baselineEnergy', FADE), 'dB'),
      },
      {
        kind: 'unavailable',
        label: 'Microphone distance',
        detail: 'Cannot be separated from a real drop in vocal effort without a calibrated recording.',
      },
    ],
    limitations: ['Low confidence: recording conditions could explain this drop.'],
  },
]

export const demoAnalysis: AnalysisResult = {
  id: 'demo-fixture-001',
  isDemo: true,
  label: 'Demo fixture',
  provenance:
    'Hand-authored sample data generated by deterministic formulas in the frontend. Not computed from any recording.',
  durationSec: DURATION,
  transcript:
    'Good morning everyone. Today I want to walk through what we learned, and that is why the second quarter matters more than any other. It matters because the, the results were not what we expected. We tested three approaches, compared them, and chose the simplest one. It held up under every check we ran, and that is what I would recommend going forward.',
  peaks: buildPeaks(240),
  frames,
  findings,
  coachTips: [
    {
      id: 't-pace',
      findingId: 'f-pace',
      action: 'Slow down on the sentence that carries your main claim.',
      drill: 'Re-record this sentence aiming for one clear beat between each phrase, then compare the speech rate.',
      rationale: 'Triggered because measured speech rate exceeded the baseline in this interval.',
      source: 'rule-based',
    },
    {
      id: 't-pause',
      findingId: 'f-pause',
      action: 'Finish the phrase before pausing.',
      drill: 'Mark the transcript with intended pause points at commas and full stops, then rehearse to those marks.',
      rationale: 'Triggered because a silent gap was measured mid-phrase where the baseline has none.',
      source: 'rule-based',
    },
    {
      id: 't-monotone',
      findingId: 'f-monotone',
      action: 'Lift your pitch on the contrasting items in the list.',
      drill: 'Read the three-item list aloud, deliberately stepping the pitch up on each item and down at the end.',
      rationale: 'Triggered because measured pitch range was narrower than the baseline in this interval.',
      source: 'rule-based',
    },
    {
      id: 't-energy',
      findingId: 'f-energy',
      action: 'Carry your volume through to the final word.',
      drill: 'Take a breath before the closing sentence and re-record it at a steady distance from the microphone.',
      rationale:
        'Triggered because measured energy fell below the baseline. Confidence is low, so check your recording setup first.',
      source: 'rule-based',
    },
  ],
  limitations: [
    'This is demo data. No audio was analysed to produce it.',
    'Word-level alignment is not included in the fixture.',
    'Coaching text is fixed, rule-based sample text. No language model is connected.',
  ],
}
