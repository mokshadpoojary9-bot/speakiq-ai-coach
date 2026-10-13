import type { AnalyzeResponse, WordAlignmentStatus } from '../lib/api'
import { formatPercent, formatTime } from '../lib/format'
import { describeTranscript } from './RealReport'
import { Badge, EmptyState } from './ui'

interface DisplayWord {
  key: string
  word: string
  status: WordAlignmentStatus | 'recognized'
  start: number | null
  end: number | null
  recognizedAs: string | null
}

const chipClass: Record<DisplayWord['status'], string> = {
  recognized: 'border-line',
  aligned: 'border-accent/40',
  substituted: 'border-warn/50',
  unaligned: 'border-dashed border-line text-muted',
}

function Unavailable({ title, message }: { title: string; message: string | null }) {
  return (
    <div role="status" className="rounded-lg border border-warn/40 bg-warn/5 p-4">
      <p className="text-sm font-semibold text-warn">{title}</p>
      {message && <p className="mt-1 text-sm text-muted">{message}</p>}
    </div>
  )
}

/** Transcript and word-level timestamps exactly as the backend returned them. */
export function TranscriptPanel({
  result,
  onSeek,
}: {
  result: AnalyzeResponse
  /** When given, words with a time become buttons that jump playback there. */
  onSeek?: (time: number) => void
}) {
  const { transcription, alignment, components } = result

  if (!transcription) {
    return (
      <Unavailable
        title={components.transcription.status === 'failed' ? 'Transcription failed' : 'Transcription is unavailable'}
        message={components.transcription.message}
      />
    )
  }
  if (transcription.status === 'no_speech') {
    return (
      <EmptyState
        title="No speech was recognised"
        description="The transcription model did not find any words in this recording, so there is no transcript and no word timing."
      />
    )
  }

  const supplied = alignment?.transcript_source === 'supplied'
  const words: DisplayWord[] =
    alignment && supplied
      ? alignment.words.map((w) => ({
          key: `a-${w.index}`,
          word: w.word,
          status: w.status,
          start: w.start,
          end: w.end,
          recognizedAs: w.recognized_as,
        }))
      : transcription.words.map((w, i) => ({
          key: `r-${i}`,
          word: w.word,
          status: 'recognized',
          start: w.start,
          end: w.end,
          recognizedAs: null,
        }))

  return (
    <div className="flex flex-col gap-5">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-xs font-semibold tracking-widest text-muted uppercase">Recognised text</h3>
          <Badge>
            {transcription.engine} · {transcription.model}
            {transcription.language && ` · ${transcription.language}`}
          </Badge>
        </div>
        <p className="mt-2 text-sm leading-relaxed">{transcription.text}</p>
        <p className="mt-2 text-xs text-muted">
          Produced by a speech-recognition model, so it can contain errors.
        </p>
      </div>

      <div>
        <h3 className="text-xs font-semibold tracking-widest text-muted uppercase">
          {supplied ? 'Your transcript, word by word' : 'Word timestamps'}
        </h3>
        <p className="mt-2 text-xs text-muted">
          Transcript used:{' '}
          {describeTranscript(
            result.transcripts ? (result.transcripts.shared_for_comparison ?? result.transcripts.participant) : undefined,
          )}
          .
        </p>

        {supplied && alignment && (
          <p className="mt-2 text-sm text-muted">
            {alignment.aligned_count} of {alignment.word_count} words aligned ({formatPercent(alignment.coverage)})
            {alignment.substituted_count > 0 && `, ${alignment.substituted_count} heard as a different word`}
            {alignment.unaligned_count > 0 && `, ${alignment.unaligned_count} with no time`}.
          </p>
        )}
        {!alignment && components.alignment.message && (
          <div className="mt-2">
            <Unavailable title="Alignment is unavailable" message={components.alignment.message} />
          </div>
        )}

        {words.length === 0 ? (
          <div className="mt-3">
            <EmptyState
              title="No word-level timestamps"
              description="The model returned text without a time for each word."
            />
          </div>
        ) : (
          <ol className="mt-3 flex flex-wrap gap-1.5" aria-label="Words with timestamps">
            {words.map((w) => {
              const time = w.start === null || w.end === null ? 'no time' : `${formatTime(w.start)}–${formatTime(w.end)}`
              const content = (
                <>
                  <span className="block text-sm">{w.word}</span>
                  <span className="block font-mono text-[10px] text-muted">
                    {time}
                    {w.recognizedAs && ` · heard “${w.recognizedAs}”`}
                  </span>
                </>
              )
              const className = `rounded-md border bg-ink-900 px-2 py-1 text-left ${chipClass[w.status]}`
              return (
                <li key={w.key}>
                  {onSeek && w.start !== null ? (
                    <button
                      type="button"
                      className={`${className} transition-colors hover:border-accent`}
                      onClick={() => onSeek(w.start as number)}
                      aria-label={`${w.word}, ${time}. Play from here`}
                    >
                      {content}
                    </button>
                  ) : (
                    <div className={className}>{content}</div>
                  )}
                </li>
              )
            })}
          </ol>
        )}

        {supplied && alignment && alignment.unmatched_recognized.length > 0 && (
          <p className="mt-3 text-sm text-muted">
            Heard but not in your transcript:{' '}
            {alignment.unmatched_recognized.map((w) => `“${w.word}” (${formatTime(w.start)})`).join(', ')}
          </p>
        )}
        <p className="mt-3 text-xs text-muted">
          Times come from the recognition model and are accurate to roughly a tenth of a second.
          {supplied && ' Words without a time were not matched; no time is guessed for them.'}
        </p>
      </div>
    </div>
  )
}
