import type { ReactNode } from 'react'
import { severityColor, severityLabel } from '../lib/theme'
import type { MetricStatus } from '../lib/api'
import type { EvidenceKind, Severity } from '../types'

const btnBase =
  'inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50'
export const btnPrimary = `${btnBase} bg-accent text-ink-950 hover:bg-[#5ad9a1]`
export const btnSecondary = `${btnBase} border border-line bg-ink-800 text-fg hover:border-muted/60 hover:bg-ink-700`

export function Card({
  children,
  className = '',
  as: Tag = 'section',
  ...rest
}: {
  children: ReactNode
  className?: string
  as?: 'section' | 'div' | 'article'
  'aria-labelledby'?: string
  'aria-label'?: string
}) {
  return (
    <Tag className={`min-w-0 rounded-xl border border-line bg-ink-800 p-5 sm:p-6 ${className}`} {...rest}>
      {children}
    </Tag>
  )
}

type Tone = 'neutral' | 'accent' | 'warn'
const toneClass: Record<Tone, string> = {
  neutral: 'border-line text-muted',
  accent: 'border-accent/40 text-accent',
  warn: 'border-warn/40 text-warn',
}

export function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: Tone }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium whitespace-nowrap ${toneClass[tone]}`}
    >
      {children}
    </span>
  )
}

/** Must accompany every view that shows fixture data. */
export function DemoBadge() {
  return (
    <Badge tone="warn">
      <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-warn" />
      Demo data — not a real analysis
    </Badge>
  )
}

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium whitespace-nowrap"
      style={{ color: severityColor[severity], borderColor: `${severityColor[severity]}66` }}
    >
      {severityLabel[severity]} severity
    </span>
  )
}

const evidenceKindLabel: Record<EvidenceKind, string> = {
  measured: 'Measured',
  inferred: 'Inferred',
  unavailable: 'Unavailable',
}
const evidenceKindTone: Record<EvidenceKind, Tone> = {
  measured: 'accent',
  inferred: 'warn',
  unavailable: 'neutral',
}

export function EvidenceKindBadge({ kind }: { kind: EvidenceKind }) {
  return <Badge tone={evidenceKindTone[kind]}>{evidenceKindLabel[kind]}</Badge>
}

const metricStatusLabel: Record<MetricStatus, string> = {
  measured: 'Measured',
  estimated: 'Estimated',
  unavailable: 'Unavailable',
}
const metricStatusTone: Record<MetricStatus, Tone> = { measured: 'accent', estimated: 'warn', unavailable: 'neutral' }

/** Status the backend reported for one real metric. */
export function MetricStatusBadge({ status }: { status: MetricStatus }) {
  return <Badge tone={metricStatusTone[status]}>{metricStatusLabel[status]}</Badge>
}

/** Marks a view that shows a real backend analysis rather than the demo fixture. */
export function LiveBadge({ filename }: { filename: string }) {
  return (
    <Badge tone="accent">
      <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-accent" />
      Real analysis · {filename}
    </Badge>
  )
}

export function PageHeader({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow?: string
  title: string
  description?: string
  children?: ReactNode
}) {
  return (
    <header className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="max-w-2xl">
        {eyebrow && <p className="mb-2 text-xs font-semibold tracking-widest text-accent uppercase">{eyebrow}</p>}
        <h1 className="text-3xl font-semibold sm:text-4xl">{title}</h1>
        {description && <p className="mt-3 text-base leading-relaxed text-muted">{description}</p>}
      </div>
      {children && <div className="flex flex-wrap items-center gap-3">{children}</div>}
    </header>
  )
}

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <div role="status" className="flex items-center justify-center gap-3 rounded-xl border border-line bg-ink-800 p-10 text-sm text-muted">
      <span
        aria-hidden="true"
        className="h-4 w-4 animate-spin rounded-full border-2 border-line border-t-accent"
      />
      {label}
    </div>
  )
}

export function EmptyState({ title, description, children }: { title: string; description?: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-line p-8 text-center">
      <p className="text-sm font-medium text-fg">{title}</p>
      {description && <p className="max-w-md text-sm text-muted">{description}</p>}
      {children && <div className="mt-2">{children}</div>}
    </div>
  )
}

export function ErrorState({
  title = 'Something went wrong',
  message,
  onRetry,
}: {
  title?: string
  message: string
  onRetry?: () => void
}) {
  return (
    <div role="alert" className="flex flex-col items-start gap-3 rounded-xl border border-danger/40 bg-danger/5 p-5">
      <div>
        <p className="text-sm font-semibold text-danger">{title}</p>
        <p className="mt-1 text-sm text-muted">{message}</p>
      </div>
      {onRetry && (
        <button type="button" className={btnSecondary} onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  )
}
