import type { Severity } from '../types'

// Mirrors the tokens in index.css for places that need raw values (SVG, charts, WebGL).
export const colors = {
  ink900: '#0b0f0d',
  ink800: '#111715',
  ink700: '#19221e',
  line: '#25322c',
  fg: '#e8eeea',
  muted: '#9fada6',
  accent: '#3ecf8e',
  baseline: '#7d8a84',
  warn: '#e5b454',
  danger: '#f07f7a',
} as const

export const severityColor: Record<Severity, string> = {
  high: colors.danger,
  medium: colors.warn,
  low: '#8fb8d8',
}

export const severityLabel: Record<Severity, string> = {
  high: 'High',
  medium: 'Medium',
  low: 'Low',
}
