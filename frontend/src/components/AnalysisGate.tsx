import type { ReactNode } from 'react'
import { useAnalysis, type AnalysisLoader } from '../lib/useAnalysis'
import type { AnalysisResult } from '../types'
import { ErrorState, LoadingState } from './ui'

/** Handles the loading and error states shared by every page that shows an analysis. */
export function AnalysisGate({
  loader,
  children,
}: {
  loader?: AnalysisLoader
  children: (analysis: AnalysisResult) => ReactNode
}) {
  const { state, retry } = useAnalysis(loader)

  if (state.status === 'loading') return <LoadingState label="Loading analysis…" />
  if (state.status === 'error') {
    return <ErrorState title="Could not load the analysis" message={state.message} onRetry={retry} />
  }
  return <>{children(state.data)}</>
}
