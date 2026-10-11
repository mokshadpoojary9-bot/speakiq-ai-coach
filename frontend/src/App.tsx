import { HealthStatus } from './components/HealthStatus'

export default function App() {
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center gap-4 px-6">
      <h1 className="text-4xl font-semibold tracking-tight">SpeakIQ AI Coach</h1>
      <p className="text-zinc-400">
        Evidence-first speech delivery analysis with temporally grounded explanations.
      </p>
      <HealthStatus />
    </main>
  )
}
