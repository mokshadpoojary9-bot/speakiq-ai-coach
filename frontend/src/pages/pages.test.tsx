import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { demoAnalysis } from '../fixtures/demoAnalysis'
import Coach from './Coach'
import Dashboard from './Dashboard'
import Reports from './Reports'
import Workspace, { MAX_AUDIO_BYTES, validateAudioFile } from './Workspace'

vi.mock('wavesurfer.js', () => ({
  default: {
    create: () => ({
      on: (event: string, callback: (seconds: number) => void) => {
        if (event === 'ready') queueMicrotask(() => callback(12.5))
      },
      destroy: () => {},
      playPause: () => {},
    }),
  },
}))

const renderPage = (page: ReactNode) => render(<MemoryRouter>{page}</MemoryRouter>)

describe('Dashboard', () => {
  it('labels the data as demo and lists every fixture finding', async () => {
    renderPage(<Dashboard />)

    expect(screen.getByText(/Demo data — not a real analysis/)).toBeInTheDocument()
    const list = await screen.findByRole('region', { name: 'Findings' })
    for (const finding of demoAnalysis.findings) {
      expect(within(list).getByRole('button', { name: new RegExp(finding.title) })).toBeInTheDocument()
    }
  })

  it('shows evidence, confidence and limitations for the selected finding', async () => {
    const user = userEvent.setup()
    renderPage(<Dashboard />)
    const list = await screen.findByRole('region', { name: 'Findings' })

    await user.click(within(list).getByRole('button', { name: /Trailing energy drop/ }))

    const detail = screen.getByRole('region', { name: 'Selected finding' })
    expect(within(detail).getByRole('heading', { name: 'Trailing energy drop' })).toBeInTheDocument()
    expect(within(detail).getByText(/· low confidence/)).toBeInTheDocument()
    expect(within(detail).getByText('Measured')).toBeInTheDocument()
    expect(within(detail).getByText('Unavailable')).toBeInTheDocument()
    expect(within(detail).getByText(/recording conditions could explain/i)).toBeInTheDocument()
  })

  it('selects a finding from the waveform timeline and filters by severity', async () => {
    const user = userEvent.setup()
    renderPage(<Dashboard />)
    await screen.findByRole('region', { name: 'Findings' })

    await user.click(screen.getByRole('button', { name: /^Flat pitch, 0:13.0/ }))
    expect(
      within(screen.getByRole('region', { name: 'Selected finding' })).getByRole('heading', { name: 'Flat pitch' }),
    ).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'High' }))
    const list = screen.getByRole('region', { name: 'Findings' })
    expect(within(list).getByRole('button', { name: /Rushed delivery/ })).toBeInTheDocument()
    expect(within(list).queryByRole('button', { name: /Flat pitch/ })).not.toBeInTheDocument()
    expect(screen.getByText('No finding selected')).toBeInTheDocument()
  })
})

describe('Evidence Coach', () => {
  it('shows rule-based advice with its rationale for the chosen finding', async () => {
    const user = userEvent.setup()
    renderPage(<Coach />)

    expect(await screen.findByText('Slow down on the sentence that carries your main claim.')).toBeInTheDocument()
    expect(screen.getByText(/Rule-based · no language model/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Long hesitation pause/ }))

    expect(screen.getByText('Finish the phrase before pausing.')).toBeInTheDocument()
    expect(screen.getByText(/silent gap was measured mid-phrase/)).toBeInTheDocument()
  })

  it('keeps free-form questions disabled and explains why', async () => {
    renderPage(<Coach />)

    const input = await screen.findByLabelText('Your question')
    expect(input).toBeDisabled()
    expect(input).toHaveAccessibleDescription(/neither of which is connected/)
  })
})

describe('Reports', () => {
  it('previews a demo-labelled report with findings, recommendations and limitations', async () => {
    renderPage(<Reports />)

    const report = await screen.findByRole('article', { name: 'Speech delivery report' })
    expect(within(report).getByText(/Demo data — not a real analysis/)).toBeInTheDocument()
    expect(within(report).getByText('1. Rushed delivery')).toBeInTheDocument()
    expect(within(report).getByText('Slow down on the sentence that carries your main claim.')).toBeInTheDocument()
    expect(within(report).getByText(/No audio was analysed to produce it/)).toBeInTheDocument()
  })

  it('prints through the browser', async () => {
    const print = vi.fn()
    vi.stubGlobal('print', print)
    renderPage(<Reports />)

    await userEvent.click(screen.getByRole('button', { name: 'Print or save as PDF' }))

    expect(print).toHaveBeenCalledOnce()
  })
})

describe('Workspace', () => {
  const audio = (name = 'talk.wav', type = 'audio/wav') => new File([new Uint8Array(2048)], name, { type })

  it('starts empty with analysis disabled', () => {
    renderPage(<Workspace />)

    expect(screen.getByText('No audio selected yet')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Run analysis' })).toBeDisabled()
  })

  it('rejects a non-audio file with an error', () => {
    renderPage(<Workspace />)

    fireEvent.change(screen.getByLabelText(/^Audio file/), {
      target: { files: [new File(['hello'], 'notes.pdf', { type: 'application/pdf' })] },
    })

    expect(screen.getByRole('alert')).toHaveTextContent(/notes.pdf.*is not a supported audio file/)
    expect(screen.getByRole('button', { name: 'Run analysis' })).toBeDisabled()
  })

  it('previews a valid file and says plainly that analysis is not available', async () => {
    const user = userEvent.setup()
    renderPage(<Workspace />)

    fireEvent.change(screen.getByLabelText(/^Audio file/), { target: { files: [audio()] } })
    expect(screen.getByText('talk.wav')).toBeInTheDocument()
    expect(await screen.findByText('Duration 0:12.5')).toBeInTheDocument()

    await user.type(screen.getByLabelText('The text you were delivering'), 'Good morning everyone')
    expect(screen.getByText('3 words')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Run analysis' }))

    expect(screen.getByText('Analysis isn’t available in this build')).toBeInTheDocument()
    expect(screen.getByText(/nothing was uploaded or analysed/)).toBeInTheDocument()
  })

  it('validates type, emptiness and size', () => {
    expect(validateAudioFile(audio())).toBeNull()
    expect(validateAudioFile(audio('clip.MP3', ''))).toBeNull()
    expect(validateAudioFile(new File([], 'empty.wav', { type: 'audio/wav' }))).toMatch(/is empty/)
    const big = audio()
    Object.defineProperty(big, 'size', { value: MAX_AUDIO_BYTES + 1 })
    expect(validateAudioFile(big)).toMatch(/The limit is 25.0 MB/)
  })
})
