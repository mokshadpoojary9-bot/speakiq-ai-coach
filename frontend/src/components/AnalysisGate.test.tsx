import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { demoAnalysis } from '../fixtures/demoAnalysis'
import { AnalysisGate } from './AnalysisGate'
import { FindingList } from './Findings'

describe('AnalysisGate', () => {
  it('shows a loading state, then the content', async () => {
    const loader = () => Promise.resolve(demoAnalysis)
    render(<AnalysisGate loader={loader}>{(a) => <p>{a.label}</p>}</AnalysisGate>)

    expect(screen.getByRole('status')).toHaveTextContent('Loading analysis…')
    expect(await screen.findByText('Demo fixture')).toBeInTheDocument()
  })

  it('shows an error state and recovers on retry', async () => {
    const loader = vi
      .fn()
      .mockRejectedValueOnce(new Error('fixture failed to load'))
      .mockResolvedValueOnce(demoAnalysis)
    render(<AnalysisGate loader={loader}>{(a) => <p>{a.label}</p>}</AnalysisGate>)

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Could not load the analysis')
    expect(alert).toHaveTextContent('fixture failed to load')

    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))

    expect(await screen.findByText('Demo fixture')).toBeInTheDocument()
    expect(loader).toHaveBeenCalledTimes(2)
  })
})

describe('FindingList', () => {
  it('shows an empty state when there are no findings', () => {
    render(<FindingList findings={[]} selectedId={null} onSelect={() => {}} />)

    expect(screen.getByText('No findings to show')).toBeInTheDocument()
  })
})
