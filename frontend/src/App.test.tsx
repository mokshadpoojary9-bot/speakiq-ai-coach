import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from './App'

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  )
}

describe('App shell and navigation', () => {
  it('renders the landing page with a skip link and primary navigation', () => {
    renderAt('/')

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(/exactly where/i)
    expect(screen.getByRole('link', { name: 'Skip to main content' })).toHaveAttribute('href', '#main')
    const nav = screen.getByRole('navigation', { name: 'Primary' })
    for (const name of ['Workspace', 'Dashboard', 'Acoustic Twin', 'Evidence Coach', 'Reports']) {
      expect(within(nav).getByRole('link', { name })).toBeInTheDocument()
    }
  })

  it('states on the landing page that analysis views use demo data', () => {
    renderAt('/')

    expect(screen.getByText(/analysis engine is not connected yet/i)).toBeInTheDocument()
  })

  it('navigates to each page and marks the active link', async () => {
    const user = userEvent.setup()
    renderAt('/')
    const nav = screen.getByRole('navigation', { name: 'Primary' })

    const pages: Array<[string, string]> = [
      ['Workspace', 'Prepare a recording'],
      ['Dashboard', 'Analysis'],
      ['Acoustic Twin', 'Your delivery, side by side with the baseline'],
      ['Evidence Coach', 'Advice you can trace back'],
      ['Reports', 'Report preview'],
    ]
    for (const [link, heading] of pages) {
      await user.click(within(nav).getByRole('link', { name: link }))
      // Pages are lazy-loaded; the first import of the chart and 3D pages can take a few seconds.
      expect(await screen.findByRole('heading', { level: 1, name: heading }, { timeout: 15000 })).toBeInTheDocument()
      expect(within(nav).getByRole('link', { name: link })).toHaveAttribute('aria-current', 'page')
    }
  }, 60000)

  it('shows a not-found page for unknown routes', () => {
    renderAt('/nope')

    expect(screen.getByText('Page not found')).toBeInTheDocument()
  })

  it('reports the backend as unreachable when the health check fails', async () => {
    renderAt('/')

    expect(await screen.findByText('Backend not reachable')).toBeInTheDocument()
  })
})
