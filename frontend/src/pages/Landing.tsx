import { Link } from 'react-router-dom'
import { Badge, btnPrimary, btnSecondary, Card, EvidenceKindBadge } from '../components/ui'

const evidenceKinds = [
  {
    kind: 'measured' as const,
    title: 'Measured facts',
    body: 'Values computed from the audio: pitch contour, energy, speech rate and pause intervals, each compared with a baseline delivery of the same transcript.',
  },
  {
    kind: 'inferred' as const,
    title: 'Inferred explanations',
    body: 'Interpretations of what a measurement probably means for a listener. Always labelled as inference, never presented as fact.',
  },
  {
    kind: 'unavailable' as const,
    title: 'Unavailable evidence',
    body: 'What could not be checked, such as missing word alignment or uncalibrated recordings, stated plainly instead of guessed.',
  },
]

const steps = [
  {
    title: 'Upload a recording and its transcript',
    body: 'Bring the audio you want reviewed and the text you were delivering.',
    status: 'Works today: real measurements, transcript and word timing',
  },
  {
    title: 'Contrast against a baseline',
    body: 'The same transcript, delivered well, becomes the reference for pitch, energy, pace and pauses.',
    status: 'Shown with demo data',
  },
  {
    title: 'See every flaw on the timeline',
    body: 'Each finding carries a start and end time, its supporting evidence, a confidence level and its limitations.',
    status: 'Shown with demo data',
  },
  {
    title: 'Get coaching tied to the evidence',
    body: 'Advice links back to the interval and measurement that triggered it, with a rule-based fallback when no language model is configured.',
    status: 'Shown with demo data',
  },
]

export default function Landing() {
  return (
    <div className="flex flex-col gap-20">
      <section className="animate-rise pt-4 sm:pt-10">
        <Badge tone="accent">Contrastive speech analytics · Temporal flaw grounding</Badge>
        <h1 className="mt-6 max-w-3xl text-4xl leading-[1.08] font-semibold sm:text-6xl">
          Speech coaching that shows you <span className="text-accent">exactly where</span>, and why.
        </h1>
        <p className="mt-6 max-w-2xl text-lg leading-relaxed text-muted">
          SpeakIQ AI Coach compares your delivery with a baseline of the same words and pins every flaw to a specific
          moment in the audio, with the evidence behind it and an honest account of what it could not measure.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <Link to="/workspace" className={btnPrimary}>
            Open the workspace
          </Link>
          <Link to="/dashboard" className={btnSecondary}>
            Explore the demo analysis
          </Link>
        </div>
        <p className="mt-6 max-w-2xl text-sm text-muted">
          <strong className="font-medium text-warn">Early build.</strong> Uploading a recording gives you real acoustic
          measurements, a transcript and word timing. Baseline comparison, flaw detection and coaching are not built
          yet; those views run on a clearly labelled demo fixture.
        </p>
      </section>

      <section aria-labelledby="evidence-heading">
        <h2 id="evidence-heading" className="text-2xl font-semibold sm:text-3xl">
          Three kinds of evidence, never blurred
        </h2>
        <div className="mt-6 grid gap-4 md:grid-cols-3">
          {evidenceKinds.map((item) => (
            <Card key={item.kind} as="article">
              <EvidenceKindBadge kind={item.kind} />
              <h3 className="mt-4 text-lg font-semibold">{item.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted">{item.body}</p>
            </Card>
          ))}
        </div>
      </section>

      <section aria-labelledby="how-heading">
        <h2 id="how-heading" className="text-2xl font-semibold sm:text-3xl">
          How it works
        </h2>
        <ol className="mt-6 grid gap-4 md:grid-cols-2">
          {steps.map((step, index) => (
            <li key={step.title} className="rounded-xl border border-line bg-ink-800 p-5 sm:p-6">
              <span className="font-mono text-sm text-accent">{String(index + 1).padStart(2, '0')}</span>
              <h3 className="mt-2 text-lg font-semibold">{step.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted">{step.body}</p>
              <p className="mt-4 text-xs text-muted">{step.status}</p>
            </li>
          ))}
        </ol>
      </section>
    </div>
  )
}
