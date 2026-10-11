import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'

afterEach(() => vi.unstubAllGlobals())

describe('App', () => {
  it('shows the product name and a live backend status', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ status: 'ok', service: 'speakiq-ai-coach-backend', version: '0.1.0', environment: 'test' }),
      }),
    )

    render(<App />)

    expect(screen.getByRole('heading', { name: 'SpeakIQ AI Coach' })).toBeInTheDocument()
    expect(await screen.findByText('Backend online (v0.1.0)')).toBeInTheDocument()
  })

  it('reports when the backend cannot be reached', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('network error')))

    render(<App />)

    expect(await screen.findByText('Backend not reachable')).toBeInTheDocument()
  })
})
