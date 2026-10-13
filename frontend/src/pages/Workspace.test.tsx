import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { API_BASE_URL } from '../lib/api'
import { AnalysisSessionProvider, useAnalysisSession } from '../lib/session'
import { jsonResponse, sampleAnalysis } from '../test/analysisSample'
import Workspace, { MAX_AUDIO_BYTES, validateAudioFile } from './Workspace'

vi.mock('wavesurfer.js', () => ({
  default: {
    create: () => ({
      on: (event: string, callback: (seconds: number) => void) => {
        if (event === 'ready') queueMicrotask(() => callback(4.8))
      },
      destroy: () => {},
      playPause: () => {},
    }),
  },
}))

const audio = (name = 'talk.wav', type = 'audio/wav') => new File([new Uint8Array(2048)], name, { type })

function SessionProbe() {
  const { session } = useAnalysisSession()
  return <p data-testid="session">{session ? session.result.features.audio.filename : 'none'}</p>
}

function renderWorkspace() {
  return render(
    <MemoryRouter>
      <AnalysisSessionProvider>
        <Workspace />
        <SessionProbe />
      </AnalysisSessionProvider>
    </MemoryRouter>,
  )
}

function chooseFile(file = audio()) {
  fireEvent.change(screen.getByLabelText(/^Audio file/), { target: { files: [file] } })
}

const run = () => userEvent.click(screen.getByRole('button', { name: 'Run analysis' }))

afterEach(() => {
  vi.mocked(fetch).mockReset()
  vi.mocked(fetch).mockRejectedValue(new TypeError('no backend in tests'))
})

describe('Workspace upload', () => {
  it('starts empty with analysis disabled', () => {
    renderWorkspace()

    expect(screen.getByText('No audio selected yet')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Run analysis' })).toBeDisabled()
    expect(fetch).not.toHaveBeenCalled()
  })

  it('rejects a file the backend cannot decode, without calling it', () => {
    renderWorkspace()

    chooseFile(new File(['hello'], 'notes.pdf', { type: 'application/pdf' }))

    expect(screen.getByRole('alert')).toHaveTextContent(/notes.pdf.*is not a supported audio file/)
    expect(screen.getByRole('button', { name: 'Run analysis' })).toBeDisabled()
    expect(fetch).not.toHaveBeenCalled()
  })

  it('validates type, emptiness and size', () => {
    expect(validateAudioFile(audio())).toBeNull()
    expect(validateAudioFile(audio('clip.MP3', ''))).toBeNull()
    expect(validateAudioFile(audio('voice.m4a', 'audio/mp4'))).toMatch(/not a supported audio file/)
    expect(validateAudioFile(new File([], 'empty.wav', { type: 'audio/wav' }))).toMatch(/is empty/)
    const big = audio()
    Object.defineProperty(big, 'size', { value: MAX_AUDIO_BYTES + 1 })
    expect(validateAudioFile(big)).toMatch(/The limit is 25.0 MB/)
  })
})

describe('Workspace analysis', () => {
  it('sends the recording and transcript to the backend and shows the returned transcript and word times', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(sampleAnalysis()))
    renderWorkspace()
    chooseFile()
    await userEvent.type(screen.getByLabelText('The text you were delivering'), 'Good morning everyone. Thank you coming')

    await run()

    const result = await screen.findByRole('region', { name: 'Analysis complete' })
    const [url, init] = vi.mocked(fetch).mock.calls[0]
    expect(url).toBe(`${API_BASE_URL}/api/analyze`)
    expect(init?.method).toBe('POST')
    const body = init?.body as FormData
    expect((body.get('file') as File).name).toBe('talk.wav')
    expect(body.get('transcript')).toBe('Good morning everyone. Thank you coming')

    expect(within(result).getByText('good morning everyone thanks for coming')).toBeInTheDocument()
    expect(within(result).getByText(/4 of 6 words aligned \(67%\), 1 heard as a different word, 1 with no time/)).toBeInTheDocument()
    const words = within(result).getByRole('list', { name: 'Words with timestamps' })
    expect(within(words).getAllByRole('listitem')).toHaveLength(6)
    expect(within(words).getByText('0:00.1–0:00.4')).toBeInTheDocument()
    expect(within(words).getByText(/0:02.9–0:03.3 · heard “thanks”/)).toBeInTheDocument()
    expect(within(words).getByText('no time')).toBeInTheDocument()
    expect(within(result).getByText(/Heard but not in your transcript: “for” \(0:03.4\)/)).toBeInTheDocument()

    expect(within(result).getByRole('link', { name: 'Open the dashboard' })).toHaveAttribute('href', '/dashboard')
    expect(within(result).getByText(/^1 finding\./)).toBeInTheDocument()
    expect(within(result).getByText(/Compared with reference.wav\./)).toBeInTheDocument()
    expect(body.has('reference')).toBe(false)
    expect(screen.getByTestId('session')).toHaveTextContent('talk.wav')
  })

  it('sends the user’s statement that they checked the transcript, and only when there is a transcript', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(sampleAnalysis()))
    renderWorkspace()
    chooseFile()
    const checkbox = screen.getByRole('checkbox', { name: /I have checked this transcript against the recording/ })
    expect(checkbox).toBeDisabled() // nothing to vouch for yet
    expect(screen.getByText(/The app cannot verify it and will not call the transcript verified/)).toBeInTheDocument()

    await run()
    await screen.findByRole('region', { name: 'Analysis complete' })
    expect((vi.mocked(fetch).mock.calls[0][1]?.body as FormData).has('transcript_reviewed')).toBe(false)

    await userEvent.type(screen.getByLabelText('The text you were delivering'), 'Good morning everyone')
    await userEvent.click(checkbox)
    await run()
    await screen.findByRole('region', { name: 'Analysis complete' })
    const body = vi.mocked(fetch).mock.calls[1][1]?.body as FormData
    expect(body.get('transcript')).toBe('Good morning everyone')
    expect(body.get('transcript_reviewed')).toBe('true')
  })

  it('sends an optional reference recording with the request', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(sampleAnalysis()))
    renderWorkspace()
    chooseFile()
    fireEvent.change(screen.getByLabelText(/^Reference recording/), { target: { files: [audio('model-take.wav')] } })
    expect(screen.getByText('model-take.wav')).toBeInTheDocument()

    await run()

    await screen.findByRole('region', { name: 'Analysis complete' })
    const body = vi.mocked(fetch).mock.calls[0][1]?.body as FormData
    expect((body.get('file') as File).name).toBe('talk.wav')
    expect((body.get('reference') as File).name).toBe('model-take.wav')
  })

  it('offers a separate reference transcript only once a reference recording is chosen, and sends it separately', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(sampleAnalysis()))
    renderWorkspace()
    chooseFile()
    expect(screen.queryByLabelText('Text of the reference recording')).not.toBeInTheDocument()

    fireEvent.change(screen.getByLabelText(/^Reference recording/), { target: { files: [audio('model-take.wav')] } })
    await userEvent.type(screen.getByLabelText('The text you were delivering'), 'my own words')
    await userEvent.type(screen.getByLabelText('Text of the reference recording'), 'the reference words')
    await userEvent.click(screen.getByRole('checkbox', { name: /I have checked this text against the reference recording/ }))
    await run()

    await screen.findByRole('region', { name: 'Analysis complete' })
    const body = vi.mocked(fetch).mock.calls[0][1]?.body as FormData
    expect(body.get('transcript')).toBe('my own words')
    expect(body.get('reference_transcript')).toBe('the reference words')
    expect(body.get('reference_transcript_reviewed')).toBe('true')
    expect(body.has('transcript_reviewed')).toBe(false) // each statement covers only its own recording
  })

  it('does not send a reference transcript without a reference recording or without text', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(sampleAnalysis()))
    renderWorkspace()
    chooseFile()
    fireEvent.change(screen.getByLabelText(/^Reference recording/), { target: { files: [audio('model-take.wav')] } })
    expect(screen.getByRole('checkbox', { name: /I have checked this text against the reference recording/ })).toBeDisabled()

    await run()

    await screen.findByRole('region', { name: 'Analysis complete' })
    const body = vi.mocked(fetch).mock.calls[0][1]?.body as FormData
    expect(body.has('reference_transcript')).toBe(false)
    expect(body.has('reference_transcript_reviewed')).toBe(false)
  })

  it('rejects an unsupported reference file without sending it', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(sampleAnalysis()))
    renderWorkspace()
    chooseFile()
    fireEvent.change(screen.getByLabelText(/^Reference recording/), {
      target: { files: [new File(['x'], 'slides.pdf', { type: 'application/pdf' })] },
    })

    expect(screen.getByRole('alert')).toHaveTextContent(/That reference file can’t be used.*slides.pdf/)
    await run()

    await screen.findByRole('region', { name: 'Analysis complete' })
    expect((vi.mocked(fetch).mock.calls[0][1]?.body as FormData).has('reference')).toBe(false)
  })

  it('summarises a result with no supported findings and one that is only partial', async () => {
    const clean = sampleAnalysis()
    clean.status = 'completed_no_findings'
    clean.findings = []
    clean.reference = null
    clean.alignment_status = { ...clean.alignment_status, status: 'no_reference', reason: 'No reference recording was supplied.' }
    const partial = sampleAnalysis()
    partial.status = 'partial'
    partial.findings = []
    partial.alignment_status = { ...partial.alignment_status, status: 'unavailable', reason: 'The two recordings were aligned to different transcripts.' }
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(clean)).mockResolvedValueOnce(jsonResponse(partial))
    renderWorkspace()
    chooseFile()

    await run()
    const first = await screen.findByRole('region', { name: 'Analysis complete' })
    expect(within(first).getByText('No supported findings.')).toBeInTheDocument()
    expect(within(first).getByText(/No reference recording was used\./)).toBeInTheDocument()

    await run()
    expect(await screen.findByText('Partial analysis.')).toBeInTheDocument()
    expect(screen.getByText(/The reference was not used: The two recordings were aligned to different transcripts\./)).toBeInTheDocument()
  })

  it('omits the transcript when none was typed and shows the recognised words instead', async () => {
    const response = sampleAnalysis()
    response.alignment = { ...response.alignment!, transcript_source: 'transcribed' }
    vi.mocked(fetch).mockResolvedValue(jsonResponse(response))
    renderWorkspace()
    chooseFile()

    await run()

    const words = await screen.findByRole('list', { name: 'Words with timestamps' })
    expect((vi.mocked(fetch).mock.calls[0][1]?.body as FormData).has('transcript')).toBe(false)
    expect(within(words).getAllByRole('listitem')).toHaveLength(6)
    expect(within(words).getByText('for')).toBeInTheDocument()
  })

  it('shows a loading state while the backend works, and can be cancelled', async () => {
    vi.mocked(fetch).mockImplementation(
      (_url, init) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
        }),
    )
    renderWorkspace()
    chooseFile()

    await run()

    expect(screen.getByRole('button', { name: 'Analysing…' })).toBeDisabled()
    expect(screen.getByText(/Uploading and analysing your recording/)).toBeInTheDocument()
    expect(screen.getByLabelText(/^Audio file/)).toBeDisabled()

    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(await screen.findByText('Analysis cancelled. No results were kept.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Run analysis' })).toBeEnabled()
    expect(screen.getByTestId('session')).toHaveTextContent('none')
  })

  it('explains when the backend is unreachable and recovers on retry', async () => {
    vi.mocked(fetch).mockRejectedValueOnce(new TypeError('Failed to fetch')).mockResolvedValueOnce(jsonResponse(sampleAnalysis()))
    renderWorkspace()
    chooseFile()

    await run()

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Can’t reach the analysis backend')
    expect(alert).toHaveTextContent(API_BASE_URL)
    expect(alert).toHaveTextContent('Your recording was not analysed')
    expect(screen.getByTestId('session')).toHaveTextContent('none')

    await userEvent.click(within(alert).getByRole('button', { name: 'Try again' }))

    expect(await screen.findByRole('region', { name: 'Analysis complete' })).toBeInTheDocument()
  })

  it('shows the backend’s own message and code when it rejects the recording', async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({ detail: { code: 'audio_too_short', message: 'The recording is 0.10 s long; at least 0.3 s is needed.' } }, 400),
    )
    renderWorkspace()
    chooseFile()

    await run()

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('The backend rejected this recording')
    expect(alert).toHaveTextContent('at least 0.3 s is needed. (code: audio_too_short)')
    expect(within(alert).queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument()
  })

  it('offers a retry for server-side failures and handles unreadable responses', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ detail: { code: 'transcription_failed', message: 'The model failed.' } }, 500))
    renderWorkspace()
    chooseFile()

    await run()
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('The backend could not analyse this recording')

    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, status: 200, json: async () => { throw new SyntaxError('bad json') } } as unknown as Response)
    await userEvent.click(within(alert).getByRole('button', { name: 'Try again' }))

    expect(await screen.findByText('Unexpected response from the backend')).toBeInTheDocument()
  })

  it('still reports measurements when transcription is unavailable on the backend', async () => {
    const response = sampleAnalysis()
    response.transcription = null
    response.alignment = null
    response.components.transcription = {
      status: 'unavailable',
      code: 'model_download_failed',
      message: "Model 'base' is not downloaded yet and could not be fetched.",
    }
    response.components.alignment = { status: 'unavailable', code: 'transcription_required', message: 'Alignment needs transcription.' }
    vi.mocked(fetch).mockResolvedValue(jsonResponse(response))
    renderWorkspace()
    chooseFile()

    await run()

    const steps = await screen.findByRole('list', { name: 'Analysis steps' })
    const [measurements, transcription] = within(steps).getAllByRole('listitem')
    expect(measurements).toHaveTextContent('Acoustic measurements' + 'Completed')
    expect(transcription).toHaveTextContent('Unavailable')
    expect(transcription).toHaveTextContent('is not downloaded yet')
    expect(screen.getByText('Transcription is unavailable')).toBeInTheDocument()
    expect(screen.queryByRole('list', { name: 'Words with timestamps' })).not.toBeInTheDocument()
  })

  it('shows an empty state when no speech was recognised', async () => {
    const response = sampleAnalysis()
    response.transcription = { ...response.transcription!, status: 'no_speech', text: '', segments: [], words: [], word_timestamps: 'unavailable' }
    response.alignment = null
    response.components.alignment = { status: 'unavailable', code: 'no_word_timestamps', message: 'No words were recognised.' }
    vi.mocked(fetch).mockResolvedValue(jsonResponse(response))
    renderWorkspace()
    chooseFile()

    await run()

    expect(await screen.findByText('No speech was recognised')).toBeInTheDocument()
    expect(screen.queryByRole('list', { name: 'Words with timestamps' })).not.toBeInTheDocument()
  })

  it('shows an empty state when the model returned text without word times', async () => {
    const response = sampleAnalysis()
    response.transcription = { ...response.transcription!, words: [], word_timestamps: 'unavailable' }
    response.alignment = null
    response.components.alignment = { status: 'unavailable', code: 'no_word_timestamps', message: 'No words with timestamps were recognised.' }
    vi.mocked(fetch).mockResolvedValue(jsonResponse(response))
    renderWorkspace()
    chooseFile()

    await run()

    expect(await screen.findByText('good morning everyone thanks for coming')).toBeInTheDocument()
    expect(screen.getByText('No word-level timestamps')).toBeInTheDocument()
    expect(screen.getByText('Alignment is unavailable')).toBeInTheDocument()
  })
})
