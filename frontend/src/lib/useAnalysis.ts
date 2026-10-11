import { useCallback, useEffect, useState } from 'react'
import type { AnalysisResult } from '../types'

export type AnalysisLoader = () => Promise<AnalysisResult>

export type AnalysisState =
  | { status: 'loading' }
  | { status: 'ready'; data: AnalysisResult }
  | { status: 'error'; message: string }

/** Until the backend exists, the only source of analysis data is the bundled demo fixture. */
export const loadDemoAnalysis: AnalysisLoader = () =>
  import('../fixtures/demoAnalysis').then((module) => module.demoAnalysis)

export function useAnalysis(loader: AnalysisLoader = loadDemoAnalysis) {
  const [state, setState] = useState<AnalysisState>({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    loader()
      .then((data) => {
        if (!cancelled) setState({ status: 'ready', data })
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setState({ status: 'error', message: error instanceof Error ? error.message : 'Unknown error' })
        }
      })
    return () => {
      cancelled = true
    }
  }, [loader, attempt])

  const retry = useCallback(() => {
    setState({ status: 'loading' })
    setAttempt((n) => n + 1)
  }, [])

  return { state, retry }
}
