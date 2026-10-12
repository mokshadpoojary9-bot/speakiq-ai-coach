// Set VITE_API_BASE_URL in frontend/.env.local (development) or the host's build settings (deployment).
export const API_BASE_URL: string = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')

export interface HealthResponse {
  status: 'ok'
  service: string
  version: string
  environment: string
}

export async function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE_URL}/api/health`, { signal })
  if (!response.ok) {
    throw new Error(`Health check failed with status ${response.status}`)
  }
  return (await response.json()) as HealthResponse
}
