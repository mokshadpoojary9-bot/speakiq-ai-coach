import { useEffect, useRef, useState } from 'react'
import WaveSurfer from 'wavesurfer.js'
import { formatTime } from '../lib/format'
import { colors } from '../lib/theme'
import { btnSecondary, ErrorState } from './ui'

/**
 * Real playback and waveform for a file the user picked. The audio is decoded in the
 * browser from an object URL; this component uploads nothing. Mount with a `key` per file.
 * Change `seek` (a new nonce each time) to jump to a time and play.
 */
export function AudioPreview({ file, seek = null }: { file: File; seek?: { time: number; nonce: number } | null }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const playerRef = useRef<WaveSurfer | null>(null)
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [playing, setPlaying] = useState(false)
  const [duration, setDuration] = useState<number | null>(null)

  useEffect(() => {
    if (!containerRef.current) return
    const url = URL.createObjectURL(file)
    const player = WaveSurfer.create({
      container: containerRef.current,
      url,
      height: 96,
      waveColor: colors.baseline,
      progressColor: colors.accent,
      cursorColor: colors.fg,
      barWidth: 2,
      barGap: 1,
      barRadius: 2,
    })
    playerRef.current = player
    player.on('ready', (seconds) => {
      setDuration(seconds)
      setStatus('ready')
    })
    player.on('error', () => setStatus('error'))
    player.on('play', () => setPlaying(true))
    player.on('pause', () => setPlaying(false))
    player.on('finish', () => setPlaying(false))

    return () => {
      player.destroy()
      URL.revokeObjectURL(url)
    }
  }, [file])

  // Jump to a requested time and play from there, e.g. when a transcript word is chosen.
  useEffect(() => {
    if (seek && status === 'ready') {
      playerRef.current?.setTime(seek.time)
      void playerRef.current?.play()
    }
  }, [seek, status])

  if (status === 'error') {
    return (
      <ErrorState
        title="This file could not be decoded"
        message="Your browser could not read it as audio. Try a WAV, MP3, M4A, OGG, FLAC or WebM file."
      />
    )
  }

  return (
    <div>
      <div ref={containerRef} className="rounded-lg border border-line bg-ink-900 px-2 py-1" aria-hidden="true" />
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button
          type="button"
          className={btnSecondary}
          disabled={status !== 'ready'}
          onClick={() => playerRef.current?.playPause()}
        >
          {playing ? 'Pause' : 'Play'}
        </button>
        <p role="status" className="font-mono text-xs text-muted">
          {status === 'loading' ? 'Decoding audio…' : `Duration ${formatTime(duration ?? 0)}`}
        </p>
      </div>
    </div>
  )
}
