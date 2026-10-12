import { createContext, useContext, useMemo, useState, type ReactNode } from 'react'
import type { AnalyzeResponse } from './api'

/** One real analysis returned by the backend, kept in memory for this browser tab only. */
export interface AnalysisSession {
  result: AnalyzeResponse
  /** The analysed file, kept so the dashboard can play it back. Never uploaded anywhere else. */
  file: File | null
  analysedAt: Date
}

interface SessionContextValue {
  session: AnalysisSession | null
  setSession: (session: AnalysisSession | null) => void
}

const SessionContext = createContext<SessionContextValue>({ session: null, setSession: () => {} })

export function AnalysisSessionProvider({
  children,
  initial = null,
}: {
  children: ReactNode
  initial?: AnalysisSession | null
}) {
  const [session, setSession] = useState<AnalysisSession | null>(initial)
  const value = useMemo(() => ({ session, setSession }), [session])
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}

export function useAnalysisSession(): SessionContextValue {
  return useContext(SessionContext)
}
