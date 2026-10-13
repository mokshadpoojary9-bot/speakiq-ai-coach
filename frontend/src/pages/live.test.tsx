import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { twinFromFeatures } from '../components/twin/twinData'
import type { AnalyzeResponse } from '../lib/api'
import { bucketMeans, hzToSemitones, thinSeries } from '../lib/measurements'
import { AnalysisSessionProvider } from '../lib/session'
import { sampleAnalysis } from '../test/analysisSample'
import Coach from './Coach'
import Dashboard from './Dashboard'
import Reports from './Reports'
import Twin from './Twin'

const player = vi.hoisted(() => ({ setTime: vi.fn(), play: vi.fn() }))

vi.mock('wavesurfer.js', () => ({
  default: {
    create: () => ({
      on: (event: string, callback: (seconds: number) => void) => {
        if (event === 'ready') queueMicrotask(() => callback(4.8))
      },
      destroy: () => {},
      playPause: () => {},
      setTime: player.setTime,
      play: player.play,
    }),
  },
}))

beforeEach(() => {
  player.setTime.mockClear()
  player.play.mockClear()
})

function renderWith(page: ReactNode, result: AnalyzeResponse | null, file: File | null = null) {
  const initial = result ? { result, file, analysedAt: new Date() } : null
  return render(
    <MemoryRouter>
      <AnalysisSessionProvider initial={initial}>{page}</AnalysisSessionProvider>
    </MemoryRouter>,
  )
}

describe('Dashboard with a real analysis', () => {
  it('shows backend measurements, labelled as real, with no demo findings', () => {
    renderWith(<Dashboard />, sampleAnalysis())

    expect(screen.getByText('Real analysis · talk.wav')).toBeInTheDocument()
    expect(screen.queryByText(/Demo data — not a real analysis/)).not.toBeInTheDocument()
    expect(screen.getByText('152 Hz')).toBeInTheDocument()
    expect(screen.getByText('3.3 syll/s')).toBeInTheDocument()
    expect(screen.getByText('estimate, not a count')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /Measured waveform of talk.wav, 0:04.8 long, with 1 finding intervals shaded/ })).toBeInTheDocument()
    expect(screen.getByText('good morning everyone thanks for coming')).toBeInTheDocument()
    // Nothing from the demo fixture's findings is shown.
    expect(screen.queryByText('Speech rate rises well above the baseline for the same sentence.')).not.toBeInTheDocument()
  })

  it('shows each real finding with its interval, evidence, severity basis and limitations', () => {
    renderWith(<Dashboard />, sampleAnalysis())
    const findings = screen.getByRole('region', { name: 'Findings' })

    expect(within(findings).getByRole('status')).toHaveTextContent('Analysis complete, with findings')
    expect(within(findings).getByText(/Compared with reference.wav over 5 of 6 words recognised in both recordings \(your transcript\)/)).toBeInTheDocument()
    const list = within(findings).getByRole('list', { name: 'Findings' })
    const [finding] = within(list).getAllByRole('listitem')
    expect(finding).toHaveTextContent('Longer pause than the reference')
    expect(finding).toHaveTextContent('0:02.0 – 0:02.8 · reference 0:01.0 – 0:01.9')
    expect(finding).toHaveTextContent('minor difference')
    expect(finding).toHaveTextContent('high evidence quality')
    const row = within(finding).getByRole('row', { name: /silence between the same words/ })
    expect(row).toHaveTextContent('silence between the same words' + '0.8' + '0.1' + 's')
    expect(finding).toHaveTextContent('pause_excess_sec = 0.4')
    expect(finding).toHaveTextContent('Severity: Extra silence beyond the reference')
    expect(finding).toHaveTextContent('A longer pause can be deliberate.')
  })

  it('lists every rule with whether it found something, found nothing, or could not check', () => {
    renderWith(<Dashboard />, sampleAnalysis())

    const rules = within(screen.getByRole('list', { name: 'Rules checked' })).getAllByRole('listitem')
    expect(rules).toHaveLength(8)
    expect(rules[0]).toHaveTextContent('Rushed delivery · Checked, nothing found')
    expect(rules[2]).toHaveTextContent('Pauses · Found (1)')
    expect(rules[3]).toHaveTextContent('Pause placement · Checked, nothing found')
    expect(rules[4]).toHaveTextContent('Uneven pacing · Could not check' + 'Needs at least 3 runs')
    expect(rules[5]).toHaveTextContent('Filler words · Checked, nothing found' + 'None were recognised.')
    expect(rules[7]).toHaveTextContent('Articulation · Not supported')
  })

  it('says which words were left out of the comparison and where the transcript came from', () => {
    renderWith(<Dashboard />, sampleAnalysis())

    expect(screen.getByText(/Left out of the comparison: 1 not recognised in participant\./)).toBeInTheDocument()
    expect(screen.getByText('Transcript used: Provided by you; not reviewed.')).toBeInTheDocument()
  })

  it('never calls a transcript verified, and says which recording the user vouched for', () => {
    const one = sampleAnalysis()
    one.transcripts.shared_for_comparison = { ...one.transcripts.shared_for_comparison!, review_status: 'not_reviewed', attested_for: ['participant'] }
    const view = renderWith(<Dashboard />, one)
    expect(
      screen.getByText(
        'Transcript used: Provided by you; you stated you checked it against your recording only, so it has not been checked against the reference (not independently verified).',
      ),
    ).toBeInTheDocument()
    view.unmount()

    const both = sampleAnalysis()
    both.transcripts.shared_for_comparison = {
      ...both.transcripts.shared_for_comparison!,
      review_status: 'user_attested',
      attested_for: ['participant', 'reference'],
    }
    renderWith(<Dashboard />, both)
    expect(
      screen.getByText('Transcript used: Provided by you; you stated you checked it against both recordings (not independently verified).'),
    ).toBeInTheDocument()
    expect(screen.queryByText(/human.verified|verified by/i)).not.toBeInTheDocument()
  })

  it('shows the participant, reference and shared transcripts separately, each with its own provenance', () => {
    const result = sampleAnalysis()
    result.transcripts = {
      participant: { source: 'user_provided', review_status: 'user_attested', human_verified: false, text: 'Good morning everyone. Thank you coming' },
      reference: { source: 'machine_generated', review_status: 'not_reviewed', human_verified: false, text: 'good morning everyone thank you coming' },
      shared_for_comparison: {
        source: 'user_provided',
        review_status: 'not_reviewed',
        human_verified: false,
        text: 'Good morning everyone. Thank you coming',
        origin: 'participant_transcript',
        attested_for: ['participant'],
      },
    }
    renderWith(<Dashboard />, result)

    const sources = within(screen.getByRole('list', { name: 'Transcript sources' })).getAllByRole('listitem')
    expect(sources).toHaveLength(2)
    expect(sources[0]).toHaveTextContent('Your recording: Provided by you; you stated you checked it against the recording (not independently verified)')
    expect(sources[1]).toHaveTextContent('Reference recording: Recognised by the speech model; not reviewed')
    // The text used to line the two up is stated separately, with where it came from.
    expect(screen.getByText(/^Transcript used: Provided by you; you stated you checked it against your recording only/)).toBeInTheDocument()
    expect(screen.getByText('Your transcript was used to line up both recordings.')).toBeInTheDocument()
  })

  it('lists only the participant transcript when there is no reference', () => {
    const result = sampleAnalysis()
    result.reference = null
    result.alignment_status = { ...result.alignment_status, status: 'no_reference' }
    result.transcripts = { ...result.transcripts, reference: null, shared_for_comparison: null }
    renderWith(<Dashboard />, result)

    const sources = within(screen.getByRole('list', { name: 'Transcript sources' })).getAllByRole('listitem')
    expect(sources).toHaveLength(1)
    expect(sources[0]).toHaveTextContent('Your recording: Provided by you; not reviewed')
  })

  it('warns when too little of the transcript could be compared to trust the comparison', () => {
    const thin = sampleAnalysis()
    thin.alignment_status = { ...thin.alignment_status, transcript_word_count: 40, words_compared: 26 }
    const view = renderWith(<Dashboard />, thin)
    const warning = screen.getByRole('note', { name: 'Comparison reliability' })
    expect(warning).toHaveTextContent('Only 26 of 40 transcript words (65%) could be compared')
    expect(warning).toHaveTextContent('recognition was unreliable for the rest')
    view.unmount()

    const solid = sampleAnalysis()
    solid.alignment_status = { ...solid.alignment_status, transcript_word_count: 40, words_compared: 36 }
    renderWith(<Dashboard />, solid)
    expect(screen.queryByRole('note', { name: 'Comparison reliability' })).not.toBeInTheDocument()
  })

  it('uses the backend’s own threshold for that warning when it reports one', () => {
    const result = sampleAnalysis()
    result.alignment_status = { ...result.alignment_status, transcript_word_count: 40, words_compared: 36 }
    result.settings = { high_quality_compared_fraction: 0.95 }
    renderWith(<Dashboard />, result)

    expect(screen.getByRole('note', { name: 'Comparison reliability' })).toHaveTextContent('Only 36 of 40 transcript words (90%)')
  })

  it('says the provenance is unknown when the backend did not report it', () => {
    const result = sampleAnalysis()
    delete (result as Partial<AnalyzeResponse>).transcripts
    const view = renderWith(<Dashboard />, result)
    expect(screen.getByText('Transcript used: Provenance unknown.')).toBeInTheDocument()
    view.unmount()

    renderWith(<Reports />, result)
    expect(within(screen.getByRole('article', { name: 'Speech delivery report' })).getByText('Provenance unknown')).toBeInTheDocument()
  })

  it('says how many words you said were not in the transcript, without counting them against you', () => {
    const result = sampleAnalysis()
    result.alignment_status = { ...result.alignment_status, unmatched_recognised: { participant: 2, reference: 0 } }
    renderWith(<Dashboard />, result)

    expect(screen.getByText(/2 words heard in your recording are not in the transcript; they were not compared and are not treated as differences\./)).toBeInTheDocument()
  })

  it('shows a finding’s interval only when its timestamps are valid', () => {
    const result = sampleAnalysis()
    result.findings = [
      result.findings[0],
      { ...result.findings[0], id: 'broken:1', title: 'Finding with no usable interval', start: 3.0, end: 3.0 },
      { ...result.findings[0], id: 'broken:2', title: 'Finding past the end of the recording', start: 9.0, end: 12.0 },
    ]
    result.coaching![0].finding_ids = result.findings.map((f) => f.id)
    const view = renderWith(<Dashboard />, result, new File([new Uint8Array(64)], 'talk.wav', { type: 'audio/wav' }))

    // Only the valid finding is drawn on the waveform or offered for playback.
    expect(screen.getByRole('img', { name: /with 1 finding intervals shaded/ })).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /^Play from / })).toHaveLength(1)
    // Direct children only: each finding also contains its own list of limitations.
    const items = Array.from(screen.getByRole('list', { name: 'Findings' }).children) as HTMLElement[]
    expect(items).toHaveLength(3)
    expect(items[0]).toHaveTextContent('0:02.0 – 0:02.8')
    expect(items[1]).toHaveTextContent('Interval unavailable')
    expect(items[2]).toHaveTextContent('Interval unavailable')
    expect(items[2]).not.toHaveTextContent('0:09.0')
    view.unmount()

    renderWith(<Coach />, result)
    const chips = within(screen.getByRole('list', { name: 'Findings behind this suggestion' })).getAllByRole('listitem')
    expect(chips.map((c) => c.textContent)).toEqual(['0:02.0 – 0:02.8', 'interval unavailable', 'interval unavailable'])
  })

  it('distinguishes a clean result with no supported findings from a partial one', () => {
    const clean = sampleAnalysis()
    clean.status = 'completed_no_findings'
    clean.findings = []
    const view = renderWith(<Dashboard />, clean)
    expect(screen.getByRole('region', { name: 'Findings' })).toHaveTextContent('Analysis complete: no supported findings')
    expect(screen.getByText('No supported findings')).toBeInTheDocument()
    expect(screen.getByText(/This does not rate the delivery as good/)).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /with 1 detected silences shaded/ })).toBeInTheDocument()
    view.unmount()

    const partial = sampleAnalysis()
    partial.status = 'partial'
    partial.findings = []
    partial.signal_quality = {
      usable: false,
      issues: [{ code: 'no_signal', level: 'blocking', message: 'The recording is silent or almost silent.', affects: [] }],
    }
    partial.alignment_status = { ...partial.alignment_status, status: 'unavailable', reason: 'The reference recording cannot be used.' }
    renderWith(<Dashboard />, partial)
    const findings = screen.getByRole('region', { name: 'Findings' })
    expect(findings).toHaveTextContent('Partial analysis')
    expect(findings).toHaveTextContent('No findings could be established')
    expect(findings).toHaveTextContent('does not mean the delivery was checked and found fine')
    expect(within(findings).getByRole('list', { name: 'Signal quality' })).toHaveTextContent('Recording not usable. The recording is silent or almost silent.')
    expect(findings).toHaveTextContent('The reference recording was not used. The reference recording cannot be used.')
  })

  it('says when no reference recording was supplied', () => {
    const result = sampleAnalysis()
    result.reference = null
    result.alignment_status = { ...result.alignment_status, status: 'no_reference' }
    renderWith(<Dashboard />, result)

    expect(screen.getByText(/No reference recording was supplied, so only the rules that need no reference were run/)).toBeInTheDocument()
  })

  it('lists each metric with the status and method the backend reported', () => {
    renderWith(<Dashboard />, sampleAnalysis())

    const methods = screen.getByRole('region', { name: 'Methods and limitations' })
    expect(within(methods).getByText('Speaking rate').closest('summary')).toHaveTextContent('Estimated')
    expect(within(methods).getByText('Pauses').closest('summary')).toHaveTextContent('Measured')
    expect(within(methods).getByText('Energy-peak syllable nuclei.')).toBeInTheDocument()
    expect(within(methods).getByText('These are acoustic measurements of one recording.')).toBeInTheDocument()
  })

  it('shows dashes and an explanation, not invented values, when pitch is unavailable', () => {
    const result = sampleAnalysis()
    result.features.pitch = {
      status: 'unavailable',
      method: 'No pitch tracker could be run.',
      limitations: ['Pitch was not computed (no tracker).'],
      series: null,
      voiced_fraction: null,
      median_hz: null,
      min_hz: null,
      max_hz: null,
      range_semitones: null,
    }
    renderWith(<Dashboard />, result)

    expect(screen.getByText('Median pitch').parentElement).toHaveTextContent('—')
    // Stated once beside the empty chart and once under the metric's method.
    expect(screen.getByText('Nothing to plot').parentElement).toHaveTextContent('Pitch was not computed (no tracker).')
    expect(screen.getAllByText('Pitch was not computed (no tracker).')).toHaveLength(2)
  })

  it('says nothing about recording quality when the backend found no problem', () => {
    renderWith(<Dashboard />, sampleAnalysis())

    expect(screen.queryByRole('list', { name: 'Recording quality notices' })).not.toBeInTheDocument()
    expect(screen.getByText('Clipping').closest('summary')).toHaveTextContent('Measured')
  })

  it('warns about detected clipping and unreliable pitch or pause measurements', () => {
    const result = sampleAnalysis()
    result.features.clipping = { ...result.features.clipping!, verdict: 'detected', flat_top_runs: 412 }
    result.features.pitch = {
      ...result.features.pitch,
      reliability: 'low',
      limitations: ['Low reliability: 3.0% of frame-to-frame steps leap more than 8 semitones.'],
    }
    result.features.pauses = {
      ...result.features.pauses,
      reliability: 'low',
      limitations: ['Low confidence: speech is only 9 dB above the background.'],
    }
    renderWith(<Dashboard />, result)

    const notices = within(screen.getByRole('list', { name: 'Recording quality notices' })).getAllByRole('listitem')
    expect(notices).toHaveLength(3)
    expect(notices[0]).toHaveTextContent('Clipping detected. The recording has 412 flat-topped peaks')
    expect(notices[1]).toHaveTextContent('Pitch tracking is unreliable for this recording. Low reliability: 3.0%')
    expect(notices[2]).toHaveTextContent('Pause detection is unreliable for this recording. Low confidence: speech is only 9 dB')
    expect(screen.getByText('measured, low reliability')).toBeInTheDocument()
    expect(screen.getByText('measured, low confidence')).toBeInTheDocument()
  })

  it('distinguishes uncertain clipping from detected clipping', () => {
    const result = sampleAnalysis()
    result.features.clipping = {
      ...result.features.clipping!,
      verdict: 'uncertain',
      limitations: ['Uncertain: the signal reaches full scale but its peaks are not flat.'],
    }
    renderWith(<Dashboard />, result)

    const notice = within(screen.getByRole('list', { name: 'Recording quality notices' })).getByRole('listitem')
    expect(notice).toHaveTextContent('Clipping could not be ruled out. Uncertain: the signal reaches full scale')
    expect(notice).not.toHaveTextContent('Clipping detected')
  })

  it('still renders results from a backend that predates the clipping check', () => {
    const result = sampleAnalysis()
    delete result.features.clipping
    renderWith(<Dashboard />, result)

    expect(screen.getByText('152 Hz')).toBeInTheDocument()
    expect(screen.queryByText('Clipping')).not.toBeInTheDocument()
  })

  it('plays from a word’s start time when the word is chosen', async () => {
    renderWith(<Dashboard />, sampleAnalysis(), new File([new Uint8Array(64)], 'talk.wav', { type: 'audio/wav' }))
    await screen.findByText('Duration 0:04.8')

    await userEvent.click(screen.getByRole('button', { name: /^Thank, 0:02.9–0:03.3/ }))

    expect(player.setTime).toHaveBeenCalledWith(2.9)
    expect(player.play).toHaveBeenCalled()

    // A finding's interval, and its band on the waveform, also start playback there.
    await userEvent.click(screen.getByRole('button', { name: 'Play from 0:02.0 – 0:02.8' }))
    expect(player.setTime).toHaveBeenLastCalledWith(2)
    await userEvent.click(screen.getByRole('button', { name: 'Longer pause than the reference, 0:02.0 – 0:02.8' }))
    expect(player.setTime).toHaveBeenCalledTimes(3)
    // A word with no time is not a button.
    expect(screen.queryByRole('button', { name: /^you,/ })).not.toBeInTheDocument()
  })

  it('lets the viewer switch to the clearly labelled demo and back', async () => {
    const user = userEvent.setup()
    renderWith(<Dashboard />, sampleAnalysis())

    await user.click(screen.getByRole('button', { name: 'Demo fixture' }))

    expect(screen.getByText(/Demo data — not a real analysis/)).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: /^Rushed delivery, 0:04.0/ })).toBeInTheDocument()
    expect(screen.queryByText('Real analysis · talk.wav')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Your recording' }))

    expect(screen.getByText('Real analysis · talk.wav')).toBeInTheDocument()
  })
})

describe('Dashboard without a real analysis', () => {
  it('shows the demo, says why, and links to the workspace', async () => {
    renderWith(<Dashboard />, null)

    expect(screen.getByText(/Demo data — not a real analysis/)).toBeInTheDocument()
    expect(screen.getByText(/No recording has been analysed in this session/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Analyse a recording' })).toHaveAttribute('href', '/workspace')
    expect(await screen.findByRole('button', { name: /^Rushed delivery, 0:04.0/ })).toBeInTheDocument()
  })
})

describe('Acoustic Twin with a real analysis', () => {
  it('draws measured energy with no baseline row or column', () => {
    renderWith(<Twin />, sampleAnalysis())

    expect(screen.getByText('Real analysis · talk.wav')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /2D Acoustic Twin.*Measured from talk.wav.*Only this recording is drawn/ })).toBeInTheDocument()
    const table = screen.getByRole('table', { hidden: true })
    expect(within(table).getAllByRole('row', { hidden: true })).toHaveLength(48 + 1)
    expect(within(table).queryByRole('columnheader', { name: /Baseline/, hidden: true })).not.toBeInTheDocument()
    expect(within(table).getByRole('columnheader', { name: 'Energy (dBFS)', hidden: true })).toBeInTheDocument()
    expect(screen.getByText('Detected pause')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Pause.*0:02.0 – 0:02.8/ })).toBeInTheDocument()
    expect(screen.getByText(/Findings from a comparison with a reference are on the dashboard, not here/)).toBeInTheDocument()
  })

  it('says there is nothing to draw when the backend returned no energy contour', () => {
    const result = sampleAnalysis()
    result.features.energy = { ...result.features.energy, status: 'unavailable', series: null, max_db: null }
    renderWith(<Twin />, result)

    expect(screen.getByText('Nothing to draw for this recording')).toBeInTheDocument()
  })

  it('maps features without filling gaps', () => {
    const twin = twinFromFeatures(sampleAnalysis().features)!

    expect(twin.source).toBe('live')
    expect(twin.hasBaseline).toBe(false)
    expect(twin.frames).toHaveLength(48)
    expect(twin.frames[0].energy).toBe(-20)
    expect(twin.frames[0].pitch).toBeCloseTo(hzToSemitones(150, 152), 2)
    expect(twin.frames[22].pitch).toBeNull() // unvoiced in the source stays empty
    expect(twin.frames.every((f) => f.baselineEnergy === undefined)).toBe(true)
    expect(twin.intervals).toEqual([expect.objectContaining({ label: 'Pause', start: 2.0, end: 2.8 })])
  })
})

describe('Evidence Coach with a real analysis', () => {
  it('shows the rule-based suggestions the backend built from the findings', () => {
    renderWith(<Coach />, sampleAnalysis())

    expect(screen.getByText('Real analysis · talk.wav')).toBeInTheDocument()
    expect(screen.queryByText(/Demo data — not a real analysis/)).not.toBeInTheDocument()
    const [tip] = within(screen.getByRole('list', { name: 'Coaching suggestions' })).getAllByRole('article')
    expect(within(tip).getByRole('heading', { level: 2 })).toHaveTextContent('Shorten the pauses at the marked points, unless you meant them.')
    expect(tip).toHaveTextContent('Rule-based · no language model')
    expect(tip).toHaveTextContent('Rehearse the phrase on either side of each marked pause as one unit')
    expect(tip).toHaveTextContent('There are 0.80 s of silence after')
    expect(within(tip).getByRole('list', { name: 'Findings behind this suggestion' })).toHaveTextContent('0:02.0 – 0:02.8')
    expect(within(tip).queryByRole('note')).not.toBeInTheDocument()
    // None of the demo fixture's advice appears.
    expect(screen.queryByText('Slow down on the sentence that carries your main claim.')).not.toBeInTheDocument()
  })

  it('shows the caution when the evidence behind a suggestion is weak', () => {
    const result = sampleAnalysis()
    result.coaching![0].caution = 'The evidence behind this is weak for this recording.'
    renderWith(<Coach />, result)

    expect(screen.getByRole('note')).toHaveTextContent('The evidence behind this is weak for this recording.')
  })

  it('explains why there is no coaching when there are no findings or the analysis was partial', () => {
    const clean = sampleAnalysis()
    clean.status = 'completed_no_findings'
    clean.findings = []
    clean.coaching = []
    const view = renderWith(<Coach />, clean)
    expect(screen.getByText('No coaching for this recording')).toBeInTheDocument()
    expect(screen.getByText(/That is not a rating of the delivery/)).toBeInTheDocument()
    view.unmount()

    const partial = sampleAnalysis()
    partial.status = 'partial'
    partial.findings = []
    partial.coaching = []
    renderWith(<Coach />, partial)
    expect(screen.getByText('No coaching: the analysis was only partial')).toBeInTheDocument()
  })

  it('can switch to the labelled demo and shows it when nothing has been analysed', async () => {
    const view = renderWith(<Coach />, sampleAnalysis())
    await userEvent.click(screen.getByRole('button', { name: 'Demo fixture' }))
    expect(screen.getByText(/Demo data — not a real analysis/)).toBeInTheDocument()
    expect(await screen.findByText('Slow down on the sentence that carries your main claim.')).toBeInTheDocument()
    view.unmount()

    renderWith(<Coach />, null)
    expect(screen.getByText(/Demo data — not a real analysis/)).toBeInTheDocument()
    expect(screen.getByText(/No recording has been analysed in this session/)).toBeInTheDocument()
  })
})

describe('Reports with a real analysis', () => {
  it('reports the status, reference, transcript provenance, findings, suggestions and what was not checked', () => {
    renderWith(<Reports />, sampleAnalysis())

    const report = screen.getByRole('article', { name: 'Speech delivery report' })
    expect(within(report).getByText('Real analysis · talk.wav')).toBeInTheDocument()
    expect(within(report).getByText('Complete, with findings')).toBeInTheDocument()
    expect(within(report).getByText('reference.wav, 5 of 6 words compared')).toBeInTheDocument()
    expect(within(report).getByText('Provided by you; not reviewed')).toBeInTheDocument()
    expect(within(report).getByText('No problems detected')).toBeInTheDocument()

    const findings = within(report).getByRole('region', { name: 'Findings (1)' })
    expect(findings).toHaveTextContent('1. Longer pause than the reference')
    expect(findings).toHaveTextContent('0:02.0 – 0:02.8 · Pauses · minor difference · high evidence quality')
    const suggestions = within(report).getByRole('region', { name: 'Suggestions (1)' })
    expect(suggestions).toHaveTextContent('Shorten the pauses at the marked points, unless you meant them.')
    expect(suggestions).toHaveTextContent('Rule-based wording; no language model was used.')
    const notChecked = within(report).getByRole('region', { name: 'Not checked' })
    expect(notChecked).toHaveTextContent('Uneven pacing: Needs at least 3 runs')
    expect(notChecked).toHaveTextContent('Articulation: No defensible measurement is available.')
    expect(within(report).queryByText(/Demo data — not a real analysis/)).not.toBeInTheDocument()
  })

  it('does not present an empty or partial result as a clean bill of health', () => {
    const partial = sampleAnalysis()
    partial.status = 'partial'
    partial.findings = []
    partial.coaching = []
    partial.alignment_status = { ...partial.alignment_status, status: 'unavailable', reason: 'The two recordings were aligned to different transcripts.' }
    partial.signal_quality = { usable: true, issues: [{ code: 'clipping_detected', level: 'warning', message: 'Clipping detected (412 flat-topped peaks).', affects: [] }] }
    renderWith(<Reports />, partial)

    const report = screen.getByRole('article', { name: 'Speech delivery report' })
    expect(within(report).getByText('Partial')).toBeInTheDocument()
    expect(within(report).getByText('Not used: The two recordings were aligned to different transcripts.')).toBeInTheDocument()
    expect(within(report).getByText('Clipping detected (412 flat-topped peaks).')).toBeInTheDocument()
    expect(within(report).getByText(/This is not a statement that the delivery was checked and found fine/)).toBeInTheDocument()
    expect(within(report).getByText('None. Suggestions are only written from findings.')).toBeInTheDocument()
  })

  it('prints through the browser and falls back to the labelled demo when nothing has been analysed', async () => {
    const print = vi.fn()
    vi.stubGlobal('print', print)
    const view = renderWith(<Reports />, sampleAnalysis())
    await userEvent.click(screen.getByRole('button', { name: 'Print or save as PDF' }))
    expect(print).toHaveBeenCalledOnce()
    view.unmount()

    renderWith(<Reports />, null)
    const demo = await screen.findByRole('article', { name: 'Speech delivery report' })
    expect(within(demo).getByText(/Demo data — not a real analysis/)).toBeInTheDocument()
  })
})

describe('measurement helpers', () => {
  const series = { unit: 'Hz', start_sec: 0, hop_sec: 0.5, values: [100, 200, null, null, 300, null] }

  it('averages values per bucket and leaves empty buckets empty', () => {
    expect(bucketMeans(series, 3, 3)).toEqual([150, null, 300])
  })

  it('thins long series by stride and keeps nulls', () => {
    expect(thinSeries(series, 3)).toEqual([
      { t: 0, value: 100 },
      { t: 1, value: null },
      { t: 2, value: 300 },
    ])
  })

  it('converts frequency ratios to semitones', () => {
    expect(hzToSemitones(200, 100)).toBeCloseTo(12)
    expect(hzToSemitones(100, 100)).toBe(0)
  })
})
