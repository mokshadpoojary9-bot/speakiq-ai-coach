import type { Interval } from '../types'

/** 75.5 -> "1:15.5" */
export function formatTime(seconds: number): string {
  const safe = Math.max(0, seconds)
  const minutes = Math.floor(safe / 60)
  const rest = safe - minutes * 60
  return `${minutes}:${rest.toFixed(1).padStart(4, '0')}`
}

export function formatInterval(interval: Interval): string {
  return `${formatTime(interval.start)} – ${formatTime(interval.end)}`
}

/**
 * A finding's interval as text, or null when its timestamps cannot be shown: missing, negative,
 * empty, reversed, or beyond the end of the recording.
 */
export function validInterval(start: number, end: number, durationSec?: number): string | null {
  const usable = Number.isFinite(start) && Number.isFinite(end) && start >= 0 && end > start
  if (!usable || (durationSec !== undefined && end > durationSec + 0.05)) return null
  return formatInterval({ start, end })
}

export function formatPercent(fraction: number): string {
  return `${Math.round(fraction * 100)}%`
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function countWords(text: string): number {
  const trimmed = text.trim()
  return trimmed ? trimmed.split(/\s+/).length : 0
}
