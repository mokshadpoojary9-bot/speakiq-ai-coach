import { useId, useState, type ChangeEvent, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { AudioPreview } from '../components/AudioPreview'
import { btnPrimary, btnSecondary, Card, EmptyState, ErrorState, PageHeader } from '../components/ui'
import { countWords, formatBytes } from '../lib/format'

export const MAX_AUDIO_BYTES = 25 * 1024 * 1024
const AUDIO_EXTENSIONS = ['.wav', '.mp3', '.m4a', '.ogg', '.flac', '.webm']

/** Returns an error message, or null when the file is acceptable. */
export function validateAudioFile(file: File): string | null {
  const name = file.name.toLowerCase()
  const looksLikeAudio = file.type.startsWith('audio/') || AUDIO_EXTENSIONS.some((ext) => name.endsWith(ext))
  if (!looksLikeAudio) {
    return `“${file.name}” is not a supported audio file. Use ${AUDIO_EXTENSIONS.join(', ')}.`
  }
  if (file.size === 0) return `“${file.name}” is empty.`
  if (file.size > MAX_AUDIO_BYTES) {
    return `“${file.name}” is ${formatBytes(file.size)}. The limit is ${formatBytes(MAX_AUDIO_BYTES)}.`
  }
  return null
}

export default function Workspace() {
  const fileInputId = useId()
  const transcriptId = useId()
  const [file, setFile] = useState<File | null>(null)
  const [fileError, setFileError] = useState<string | null>(null)
  const [transcript, setTranscript] = useState('')
  const [submitted, setSubmitted] = useState(false)

  const words = countWords(transcript)
  const ready = file !== null && words > 0

  function handleFile(event: ChangeEvent<HTMLInputElement>) {
    const picked = event.target.files?.[0] ?? null
    setSubmitted(false)
    if (!picked) return
    const error = validateAudioFile(picked)
    setFileError(error)
    setFile(error ? null : picked)
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setSubmitted(true)
  }

  return (
    <>
      <PageHeader
        eyebrow="Workspace"
        title="Prepare a recording"
        description="Choose the audio you want reviewed and paste the transcript you were delivering. Your file stays in this browser."
      />

      <form onSubmit={handleSubmit} className="grid gap-6 lg:grid-cols-2">
        <Card aria-labelledby="audio-heading">
          <h2 id="audio-heading" className="text-lg font-semibold">
            1. Audio
          </h2>
          <label htmlFor={fileInputId} className="mt-4 block text-sm text-muted">
            Audio file (WAV, MP3, M4A, OGG, FLAC or WebM, up to {formatBytes(MAX_AUDIO_BYTES)})
          </label>
          <input
            id={fileInputId}
            type="file"
            accept={`audio/*,${AUDIO_EXTENSIONS.join(',')}`}
            onChange={handleFile}
            className="mt-2 block w-full cursor-pointer rounded-lg border border-line bg-ink-900 text-sm text-muted file:mr-4 file:cursor-pointer file:border-0 file:bg-ink-700 file:px-4 file:py-2.5 file:text-sm file:font-medium file:text-fg"
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
        </Card>

        <Card aria-labelledby="transcript-heading">
          <h2 id="transcript-heading" className="text-lg font-semibold">
            2. Transcript
          </h2>
          <label htmlFor={transcriptId} className="mt-4 block text-sm text-muted">
            The text you were delivering
          </label>
          <textarea
            id={transcriptId}
            value={transcript}
            onChange={(event) => {
              setTranscript(event.target.value)
              setSubmitted(false)
            }}
            rows={10}
            placeholder="Paste or type the transcript here…"
            className="mt-2 block w-full resize-y rounded-lg border border-line bg-ink-900 p-3 text-sm leading-relaxed placeholder:text-muted/60"
          />
          <p className="mt-2 font-mono text-xs text-muted" aria-live="polite">
            {words} {words === 1 ? 'word' : 'words'}
          </p>
        </Card>

        <div className="flex flex-col gap-4 lg:col-span-2">
          <div className="flex flex-wrap items-center gap-3">
            <button type="submit" className={btnPrimary} disabled={!ready}>
              Run analysis
            </button>
            {!ready && <p className="text-sm text-muted">Add an audio file and a transcript to continue.</p>}
          </div>

          {submitted && (
            <div role="status" className="animate-rise rounded-xl border border-warn/40 bg-warn/5 p-5">
              <p className="text-sm font-semibold text-warn">Analysis isn’t available in this build</p>
              <p className="mt-1 max-w-2xl text-sm text-muted">
                The analysis backend has not been built yet, so nothing was uploaded or analysed and no results exist
                for this recording. You can explore the interface with the demo fixture instead.
              </p>
              <Link to="/dashboard" className={`${btnSecondary} mt-4`}>
                Open the demo analysis
              </Link>
            </div>
          )}
        </div>
      </form>
    </>
  )
}
