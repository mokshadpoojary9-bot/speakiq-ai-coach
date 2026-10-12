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
    expect(screen.getByRole('img', { name: /Measured waveform of talk.wav, 0:04.8 long, with 1 detected silences shaded/ })).toBeInTheDocument()
    expect(screen.getByText('good morning everyone thanks for coming')).toBeInTheDocument()

    const findings = screen.getByRole('region', { name: 'Findings' })
    expect(within(findings).getByText('No findings for this recording')).toBeInTheDocument()
    expect(within(findings).getByText(/Flaw detection and baseline comparison are not implemented yet/)).toBeInTheDocument()
    expect(screen.queryByText('Rushed delivery')).not.toBeInTheDocument()
  })

  it('lists each metric with the status and method the backend reported', () => {
    renderWith(<Dashboard />, sampleAnalysis())

    const methods = screen.getByRole('region', { name: 'Methods and limitations' })
    expect(within(methods).getByText('Speaking rate').closest('summary')).toHaveTextContent('Estimated')
    expect(within(methods).getByText('Pauses').closest('summary')).toHaveTextContent('Measured')
    expect(within(methods).getByText('Energy-peak syllable nuclei.')).toBeInTheDocument()
    expect(within(methods).getByText(/No comparison with a baseline delivery/)).toBeInTheDocument()
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

  it('plays from a word’s start time when the word is chosen', async () => {
    renderWith(<Dashboard />, sampleAnalysis(), new File([new Uint8Array(64)], 'talk.wav', { type: 'audio/wav' }))
    await screen.findByText('Duration 0:04.8')

    await userEvent.click(screen.getByRole('button', { name: /^Thank, 0:02.9–0:03.3/ }))

    expect(player.setTime).toHaveBeenCalledWith(2.9)
    expect(player.play).toHaveBeenCalled()
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
    expect(screen.getByRole('img', { name: /2D Acoustic Twin.*Measured from talk.wav.*no baseline row/ })).toBeInTheDocument()
    const table = screen.getByRole('table', { hidden: true })
    expect(within(table).getAllByRole('row', { hidden: true })).toHaveLength(48 + 1)
    expect(within(table).queryByRole('columnheader', { name: /Baseline/, hidden: true })).not.toBeInTheDocument()
    expect(within(table).getByRole('columnheader', { name: 'Energy (dBFS)', hidden: true })).toBeInTheDocument()
    expect(screen.getByText('Detected pause')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Pause.*0:02.0 – 0:02.8/ })).toBeInTheDocument()
    expect(screen.getByText(/baseline comparison and flaw detection are not implemented yet/)).toBeInTheDocument()
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

describe('Pages with no real counterpart yet', () => {
  it('warn that coaching and reports still show demo data when a recording has been analysed', () => {
    const coach = renderWith(<Coach />, sampleAnalysis())
    expect(screen.getByRole('note')).toHaveTextContent(/still shows demo data.*talk.wav.*coaching for real recordings is not implemented/)
    expect(screen.getByText(/Demo data — not a real analysis/)).toBeInTheDocument()
    coach.unmount()

    renderWith(<Reports />, sampleAnalysis())
    expect(screen.getByRole('note')).toHaveTextContent(/report generation for real recordings is not implemented/)
  })

  it('show no such warning when nothing has been analysed', () => {
    renderWith(<Coach />, null)

    expect(screen.queryByRole('note')).not.toBeInTheDocument()
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
