import { useEffect, useId, useRef, useState, type ChangeEvent, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { AudioPreview } from '../components/AudioPreview'
import { OpenSavedForm } from '../components/SavedAnalyses'
import { TranscriptPanel } from '../components/TranscriptPanel'
import { btnPrimary, btnSecondary, Card, EmptyState, ErrorState, PageHeader } from '../components/ui'
import { analyzeRecording, API_BASE_URL, ApiError, type AnalyzeResponse, type ComponentStatus } from '../lib/api'
import { countWords, formatBytes } from '../lib/format'
import { useAnalysisSession } from '../lib/session'

export const MAX_AUDIO_BYTES = 25 * 1024 * 1024
// The formats the backend can decode.
const AUDIO_EXTENSIONS = ['.wav', '.mp3', '.ogg', '.flac']

/** Returns an error message, or null when the file is acceptable. */
export function validateAudioFile(file: File): string | null {
  const name = file.name.toLowerCase()
  if (!AUDIO_EXTENSIONS.some((ext) => name.endsWith(ext))) {
    return `“${file.name}” is not a supported audio file. Use ${AUDIO_EXTENSIONS.join(', ')}.`
  }
  if (file.size === 0) return `“${file.name}” is empty.`
  if (file.size > MAX_AUDIO_BYTES) {
    return `“${file.name}” is ${formatBytes(file.size)}. The limit is ${formatBytes(MAX_AUDIO_BYTES)}.`
  }
  return null
}

type RunState =
  | { kind: 'idle' }
  | { kind: 'running'; startedAt: number }
  | { kind: 'cancelled' }
  | { kind: 'error'; error: ApiError }
  | { kind: 'done'; result: AnalyzeResponse }

function Elapsed({ startedAt }: { startedAt: number }) {
  const [seconds, setSeconds] = useState(0)
  useEffect(() => {
    const timer = setInterval(() => setSeconds(Math.floor((Date.now() - startedAt) / 1000)), 1000)
    return () => clearInterval(timer)
  }, [startedAt])
  return <span className="font-mono">{seconds}s</span>
}

const componentLabel: Record<ComponentStatus['status'], string> = {
  completed: 'Completed',
  unavailable: 'Unavailable',
  failed: 'Failed',
}

function ComponentRow({ name, component }: { name: string; component: ComponentStatus }) {
  const ok = component.status === 'completed'
  return (
    <li className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-sm">
      <span className="font-medium">{name}</span>
      <span className={ok ? 'text-accent' : 'text-warn'}>{componentLabel[component.status]}</span>
      {component.message && <span className="basis-full text-muted">{component.message}</span>}
    </li>
  )
}

function RunError({ error, onRetry }: { error: ApiError; onRetry: () => void }) {
  if (error.kind === 'network') {
    return (
      <ErrorState
        title="Can’t reach the analysis backend"
        message={`There was no response from ${API_BASE_URL}. Start the backend (in backend/: uvicorn app.main:app --port 8000), check VITE_API_BASE_URL in frontend/.env.local, then try again. Your recording was not analysed.`}
        onRetry={onRetry}
      />
    )
  }
  if (error.kind === 'invalid_response') {
    return <ErrorState title="Unexpected response from the backend" message={error.message} onRetry={onRetry} />
  }
  const serverSide = error.status !== null && error.status >= 500
  return (
    <ErrorState
      title={serverSide ? 'The backend could not analyse this recording' : 'The backend rejected this recording'}
      message={`${error.message}${error.code ? ` (code: ${error.code})` : ''}`}
      onRetry={serverSide ? onRetry : undefined}
    />
  )
}

export default function Workspace() {
  const fileInputId = useId()
  const referenceInputId = useId()
  const referenceTranscriptId = useId()
  const transcriptId = useId()
  const { setSession } = useAnalysisSession()
  const [file, setFile] = useState<File | null>(null)
  const [fileError, setFileError] = useState<string | null>(null)
  const [reference, setReference] = useState<File | null>(null)
  const [referenceError, setReferenceError] = useState<string | null>(null)
  const [transcript, setTranscript] = useState('')
  const [reviewed, setReviewed] = useState(false)
  const [referenceTranscript, setReferenceTranscript] = useState('')
  const [referenceReviewed, setReferenceReviewed] = useState(false)
  const [run, setRun] = useState<RunState>({ kind: 'idle' })
  const controller = useRef<AbortController | null>(null)

  // Stop an in-flight request if the user leaves the page.
  useEffect(() => () => controller.current?.abort(), [])

  const words = countWords(transcript)
  const running = run.kind === 'running'

  function handleFile(event: ChangeEvent<HTMLInputElement>) {
    const picked = event.target.files?.[0] ?? null
    if (!picked) return
    const error = validateAudioFile(picked)
    setFileError(error)
    setFile(error ? null : picked)
    setRun({ kind: 'idle' })
  }

  function handleReference(event: ChangeEvent<HTMLInputElement>) {
    const picked = event.target.files?.[0] ?? null
    const error = picked ? validateAudioFile(picked) : null
    setReferenceError(error)
    setReference(error ? null : picked)
    setRun({ kind: 'idle' })
  }

  async function analyse() {
    if (!file || running) return
    const current = new AbortController()
    controller.current = current
    setRun({ kind: 'running', startedAt: Date.now() })
    try {
      const result = await analyzeRecording(
        file,
        transcript,
        current.signal,
        reference,
        reviewed,
        referenceTranscript,
        referenceReviewed,
      )
      setSession({ result, file, analysedAt: new Date() })
      setRun({ kind: 'done', result })
    } catch (error) {
      if (current.signal.aborted) {
        setRun({ kind: 'cancelled' })
      } else if (error instanceof ApiError) {
        setRun({ kind: 'error', error })
      } else {
        setRun({ kind: 'error', error: new ApiError('invalid_response', 'Something unexpected went wrong in the browser.') })
      }
    }
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    void analyse()
  }

  return (
    <>
      <PageHeader
        eyebrow="Workspace"
        title="Analyse a recording"
        description="Choose a recording and, if you have it, the text you were delivering. The file is sent to your own SpeakIQ backend for analysis and is not stored."
      />

      <form onSubmit={handleSubmit} className="grid gap-6 lg:grid-cols-2">
        <Card aria-labelledby="audio-heading">
          <h2 id="audio-heading" className="text-lg font-semibold">
            1. Audio
          </h2>
          <label htmlFor={fileInputId} className="mt-4 block text-sm text-muted">
            Audio file (WAV, MP3, OGG or FLAC, up to {formatBytes(MAX_AUDIO_BYTES)})
          </label>
          <input
            id={fileInputId}
            type="file"
            accept={AUDIO_EXTENSIONS.join(',')}
            onChange={handleFile}
            disabled={running}
            className="mt-2 block w-full cursor-pointer rounded-lg border border-line bg-ink-900 text-sm text-muted file:mr-4 file:cursor-pointer file:border-0 file:bg-ink-700 file:px-4 file:py-2.5 file:text-sm file:font-medium file:text-fg disabled:cursor-not-allowed disabled:opacity-60"
          />

          <div className="mt-5">
            {fileError ? (
              <ErrorState title="That file can’t be used" message={fileError} />
            ) : file ? (
              <>
                <p className="mb-3 text-sm">
                  <span className="font-medium">{file.name}</span>
                  <span className="ml-2 font-mono text-xs text-muted">{formatBytes(file.size)}</span>
                </p>
                <AudioPreview key={`${file.name}-${file.size}-${file.lastModified}`} file={file} />
              </>
            ) : (
              <EmptyState
                title="No audio selected yet"
                description="Pick a file to hear it back and see its waveform here."
              />
            )}
          </div>

          <div className="mt-6 border-t border-line pt-5">
            <label htmlFor={referenceInputId} className="block text-sm font-medium">
              Reference recording <span className="font-normal text-muted">(optional)</span>
            </label>
            <p className="mt-1 text-sm text-muted">
              A recording of the same text to compare against. With one, pace, pauses and pitch variation are compared
              word for word. It is only what you are compared with; nothing rates it as good.
            </p>
            <input
              id={referenceInputId}
              type="file"
              accept={AUDIO_EXTENSIONS.join(',')}
              onChange={handleReference}
              disabled={running}
              className="mt-2 block w-full cursor-pointer rounded-lg border border-line bg-ink-900 text-sm text-muted file:mr-4 file:cursor-pointer file:border-0 file:bg-ink-700 file:px-4 file:py-2.5 file:text-sm file:font-medium file:text-fg disabled:cursor-not-allowed disabled:opacity-60"
            />
            {referenceError ? (
              <div className="mt-3">
                <ErrorState title="That reference file can’t be used" message={referenceError} />
              </div>
            ) : (
              reference && (
                <>
                  <p className="mt-2 text-sm">
                    <span className="font-medium">{reference.name}</span>
                    <span className="ml-2 font-mono text-xs text-muted">{formatBytes(reference.size)}</span>
                  </p>
                  <label htmlFor={referenceTranscriptId} className="mt-4 block text-sm text-muted">
                    Text of the reference recording
                  </label>
                  <textarea
                    id={referenceTranscriptId}
                    value={referenceTranscript}
                    onChange={(event) => setReferenceTranscript(event.target.value)}
                    disabled={running}
                    rows={4}
                    maxLength={20000}
                    placeholder="Optional. Leave empty if it is the same text as yours."
                    className="mt-2 block w-full resize-y rounded-lg border border-line bg-ink-900 p-3 text-sm leading-relaxed placeholder:text-muted/60 disabled:opacity-60"
                  />
                  <p className="mt-2 text-xs text-muted">
                    Kept separate from your transcript. If the two contain different words, the recordings are not
                    compared word for word and the dashboard says so.
                  </p>
                  <label className="mt-3 flex items-start gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={referenceReviewed}
                      disabled={running || countWords(referenceTranscript) === 0}
                      onChange={(event) => setReferenceReviewed(event.target.checked)}
                      className="mt-0.5 h-4 w-4 accent-[#3ecf8e]"
                    />
                    <span>
                      I have checked this text against the reference recording
                      <span className="block text-xs text-muted">Recorded as your statement; the app cannot verify it.</span>
                    </span>
                  </label>
                </>
              )
            )}
          </div>
        </Card>

        <Card aria-labelledby="transcript-heading">
          <h2 id="transcript-heading" className="text-lg font-semibold">
            2. Transcript <span className="text-sm font-normal text-muted">(optional)</span>
          </h2>
          <label htmlFor={transcriptId} className="mt-4 block text-sm text-muted">
            The text you were delivering
          </label>
          <textarea
            id={transcriptId}
            value={transcript}
            onChange={(event) => setTranscript(event.target.value)}
            disabled={running}
            rows={10}
            maxLength={20000}
            placeholder="Paste or type the transcript here…"
            className="mt-2 block w-full resize-y rounded-lg border border-line bg-ink-900 p-3 text-sm leading-relaxed placeholder:text-muted/60 disabled:opacity-60"
          />
          <p className="mt-2 font-mono text-xs text-muted" aria-live="polite">
            {words} {words === 1 ? 'word' : 'words'}
          </p>
          <p className="mt-2 text-sm text-muted">
            With a transcript, each of your words is matched to a time in the recording. Without one, the recognised
            words are timed instead.
          </p>
          <label className="mt-4 flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              checked={reviewed}
              disabled={running || words === 0}
              onChange={(event) => setReviewed(event.target.checked)}
              className="mt-0.5 h-4 w-4 accent-[#3ecf8e]"
            />
            <span>
              I have checked this transcript against the recording
              <span className="block text-xs text-muted">
                Recorded as your statement. The app cannot verify it and will not call the transcript verified.
              </span>
            </span>
          </label>
        </Card>

        <div className="flex flex-col gap-4 lg:col-span-2">
          <div className="flex flex-wrap items-center gap-3">
            <button type="submit" className={btnPrimary} disabled={!file || running}>
              {running ? 'Analysing…' : 'Run analysis'}
            </button>
            {running && (
              <button type="button" className={btnSecondary} onClick={() => controller.current?.abort()}>
                Cancel
              </button>
            )}
            {!file && !running && <p className="text-sm text-muted">Add an audio file to continue.</p>}
          </div>

          {run.kind === 'running' && (
            <div role="status" className="flex items-start gap-3 rounded-xl border border-line bg-ink-800 p-5">
              <span aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-line border-t-accent" />
              <div className="text-sm">
                <p className="font-medium">
                  Uploading and analysing your recording… <Elapsed startedAt={run.startedAt} />
                </p>
                <p className="mt-1 text-muted">
                  The backend measures the audio, transcribes it and times each word in one request, so there is no
                  step-by-step progress to show. The first run after the backend starts is slower while the speech
                  model loads.
                </p>
              </div>
            </div>
          )}

          {run.kind === 'cancelled' && (
            <p role="status" className="text-sm text-muted">
              Analysis cancelled. No results were kept.
            </p>
          )}

          {run.kind === 'error' && <RunError error={run.error} onRetry={() => void analyse()} />}

          {run.kind === 'done' && (
            <Card aria-labelledby="result-heading" className="animate-rise">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 id="result-heading" className="text-lg font-semibold">
                  Analysis complete
                </h2>
                <Link to="/dashboard" className={btnPrimary}>
                  Open the dashboard
                </Link>
              </div>
              <ul className="mt-4 flex flex-col gap-2 border-b border-line pb-5" aria-label="Analysis steps">
                <ComponentRow name="Acoustic measurements" component={run.result.components.features} />
                <ComponentRow name="Transcription" component={run.result.components.transcription} />
                <ComponentRow name="Word timing" component={run.result.components.alignment} />
              </ul>
              <div className="mt-5">
                <TranscriptPanel result={run.result} />
              </div>
              <p role="status" className="mt-5 rounded-lg border border-line bg-ink-900 px-4 py-3 text-sm">
                {run.result.status === 'partial' ? (
                  <>
                    <span className="font-semibold text-warn">Partial analysis.</span> Some checks could not run for this
                    recording; the dashboard lists which and why.
                  </>
                ) : run.result.findings.length === 0 ? (
                  <>
                    <span className="font-semibold text-accent">No supported findings.</span> Every rule that could run
                    was checked and nothing crossed its threshold.
                  </>
                ) : (
                  <>
                    <span className="font-semibold text-accent">
                      {run.result.findings.length} {run.result.findings.length === 1 ? 'finding' : 'findings'}.
                    </span>{' '}
                    Open the dashboard to see each one with its interval and evidence.
                  </>
                )}{' '}
                {run.result.alignment_status.status === 'aligned'
                  ? `Compared with ${run.result.reference?.filename ?? 'the reference'}.`
                  : run.result.alignment_status.status === 'unavailable'
                    ? `The reference was not used: ${run.result.alignment_status.reason}`
                    : 'No reference recording was used.'}
              </p>
            </Card>
          )}
        </div>
      </form>

      <details className="mt-8 rounded-xl border border-line bg-ink-800 p-5">
        <summary className="cursor-pointer rounded text-sm font-medium">Open a saved analysis</summary>
        <div className="mt-4">
          <OpenSavedForm />
        </div>
      </details>
    </>
  )
}
