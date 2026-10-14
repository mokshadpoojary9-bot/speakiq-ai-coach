import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { API_BASE_URL } from '../lib/api'
import { AnalysisSessionProvider, useAnalysisSession } from '../lib/session'
import { jsonResponse, sampleAnalysis } from '../test/analysisSample'
import { OpenSavedForm, SavePanel } from './SavedAnalyses'

const ID = '123e4567-e89b-12d3-a456-426614174000'
const KEY = 'k3y-shown-once-0123456789abcdef'
const NOT_CONFIGURED = {
  detail: {
    code: 'persistence_not_configured',
    message: 'Saving analyses is not set up on this backend. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in backend/.env to enable it.',
  },
}

afterEach(() => {
  vi.mocked(fetch).mockReset()
  vi.mocked(fetch).mockRejectedValue(new TypeError('no backend in tests'))
})

function SessionProbe() {
  const { session } = useAnalysisSession()
  return <p data-testid="session">{session ? `${session.result.features.audio.filename} file:${session.file ? 'yes' : 'none'}` : 'none'}</p>
}

const renderWithSession = (node: React.ReactNode) =>
  render(
    <MemoryRouter>
      <AnalysisSessionProvider>
        {node}
        <SessionProbe />
      </AnalysisSessionProvider>
    </MemoryRouter>,
  )

describe('SavePanel', () => {
  it('sends nothing until asked, then shows the ID and the one-time access key', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ id: ID, access_key: KEY, created_at: '2026-10-14T09:00:00+00:00' }, 201))
    const result = sampleAnalysis()
    renderWithSession(<SavePanel result={result} />)
    expect(fetch).not.toHaveBeenCalled()
    expect(screen.getByText(/The audio is never saved/)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Save this analysis' }))

    const [url, init] = vi.mocked(fetch).mock.calls[0]
    expect(url).toBe(`${API_BASE_URL}/api/analyses`)
    expect(init?.method).toBe('POST')
    expect(JSON.parse(init?.body as string)).toEqual(result)
    const saved = await screen.findByRole('status')
    expect(saved).toHaveTextContent('Saved.')
    expect(saved).toHaveTextContent(ID)
    expect(saved).toHaveTextContent(KEY)
    expect(saved).toHaveTextContent('The access key is shown only once and cannot be recovered')
  })

  it('shows the backend’s explanation when saving is not set up', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(NOT_CONFIGURED, 503))
    renderWithSession(<SavePanel result={sampleAnalysis()} />)

    await userEvent.click(screen.getByRole('button', { name: 'Save this analysis' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Not saved')
    expect(alert).toHaveTextContent('Saving analyses is not set up on this backend')
  })

  it('reports an unreachable backend', async () => {
    renderWithSession(<SavePanel result={sampleAnalysis()} />)

    await userEvent.click(screen.getByRole('button', { name: 'Save this analysis' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('The backend could not be reached.')
  })

  it('can delete what it just saved, sending the access key', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse({ id: ID, access_key: KEY, created_at: '2026-10-14T09:00:00+00:00' }, 201))
      .mockResolvedValueOnce({ ok: true, status: 204, json: async () => null } as Response)
    renderWithSession(<SavePanel result={sampleAnalysis()} />)
    await userEvent.click(screen.getByRole('button', { name: 'Save this analysis' }))

    await userEvent.click(await screen.findByRole('button', { name: 'Delete the saved copy' }))

    const [url, init] = vi.mocked(fetch).mock.calls[1]
    expect(url).toBe(`${API_BASE_URL}/api/analyses/${ID}`)
    expect(init?.method).toBe('DELETE')
    expect((init?.headers as Record<string, string>)['X-Access-Key']).toBe(KEY)
    expect(await screen.findByText('The saved copy was deleted.')).toBeInTheDocument()
  })
})

describe('OpenSavedForm', () => {
  it('opens a saved analysis into the session, without audio', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ id: ID, created_at: '2026-10-14T09:00:00+00:00', result: sampleAnalysis() }))
    renderWithSession(<OpenSavedForm />)
    expect(screen.getByRole('button', { name: 'Open' })).toBeDisabled()

    await userEvent.type(screen.getByLabelText('ID'), ID)
    await userEvent.type(screen.getByLabelText('Access key'), KEY)
    await userEvent.click(screen.getByRole('button', { name: 'Open' }))

    const [url, init] = vi.mocked(fetch).mock.calls[0]
    expect(url).toBe(`${API_BASE_URL}/api/analyses/${ID}`)
    expect((init?.headers as Record<string, string>)['X-Access-Key']).toBe(KEY)
    expect(await screen.findByRole('status')).toHaveTextContent('Opened.')
    expect(screen.getByRole('link', { name: 'View it on the dashboard' })).toHaveAttribute('href', '/dashboard')
    expect(screen.getByText(/Playback is not available because audio is never saved/)).toBeInTheDocument()
    expect(screen.getByTestId('session')).toHaveTextContent('talk.wav file:none')
    expect(screen.getByLabelText('Access key')).toHaveAttribute('type', 'password')
  })

  it('says plainly when the ID or key is wrong, without saying which', async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({ detail: { code: 'analysis_not_found', message: 'No saved analysis matches that ID and access key.' } }, 404),
    )
    renderWithSession(<OpenSavedForm />)
    await userEvent.type(screen.getByLabelText('ID'), ID)
    await userEvent.type(screen.getByLabelText('Access key'), 'wrong-key')

    await userEvent.click(screen.getByRole('button', { name: 'Open' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('No saved analysis matches that ID and access key.')
    expect(screen.getByTestId('session')).toHaveTextContent('none')
  })

  it('deletes with the ID and key', async () => {
    vi.mocked(fetch).mockResolvedValue({ ok: true, status: 204, json: async () => null } as Response)
    renderWithSession(<OpenSavedForm />)
    await userEvent.type(screen.getByLabelText('ID'), ID)
    await userEvent.type(screen.getByLabelText('Access key'), KEY)

    await userEvent.click(screen.getByRole('button', { name: 'Delete it' }))

    expect(vi.mocked(fetch).mock.calls[0][1]?.method).toBe('DELETE')
    expect(await screen.findByText('The saved analysis was deleted.')).toBeInTheDocument()
  })
})

describe('Where they appear', () => {
  it('the dashboard offers saving for a real analysis and the workspace offers opening', async () => {
    const { default: Dashboard } = await import('../pages/Dashboard')
    const { default: Workspace } = await import('../pages/Workspace')
    const initial = { result: sampleAnalysis(), file: null, analysedAt: new Date() }
    const view = render(
      <MemoryRouter>
        <AnalysisSessionProvider initial={initial}>
          <Dashboard />
        </AnalysisSessionProvider>
      </MemoryRouter>,
    )
    expect(within(screen.getByRole('region', { name: 'Save' })).getByRole('button', { name: 'Save this analysis' })).toBeInTheDocument()
    view.unmount()

    render(
      <MemoryRouter>
        <AnalysisSessionProvider>
          <Workspace />
        </AnalysisSessionProvider>
      </MemoryRouter>,
    )
    expect(screen.getByText('Open a saved analysis')).toBeInTheDocument()
    expect(fetch).not.toHaveBeenCalled()
  })
})
