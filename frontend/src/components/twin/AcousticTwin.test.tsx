import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { demoAnalysis } from '../../fixtures/demoAnalysis'
import * as webgl from '../../lib/webgl'
import { AcousticTwin } from './AcousticTwin'
import { energyToUnit, findingAt } from './twinData'

vi.mock('../../lib/webgl')
vi.mock('./TwinScene', () => ({ default: () => <div data-testid="twin-scene-3d" /> }))

afterEach(() => vi.resetAllMocks())

describe('AcousticTwin', () => {
  it('falls back to the 2D view and says why when WebGL is unavailable', () => {
    vi.mocked(webgl.detectWebGL).mockReturnValue(false)
    render(<AcousticTwin analysis={demoAnalysis} selectedId={null} />)

    expect(screen.getByRole('status')).toHaveTextContent(/WebGL is not available/)
    expect(screen.getByRole('img', { name: /2D Acoustic Twin/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '3D view' })).toBeDisabled()
    expect(screen.queryByTestId('twin-scene-3d')).not.toBeInTheDocument()
  })

  it('exposes every supplied frame in the fallback data table', () => {
    vi.mocked(webgl.detectWebGL).mockReturnValue(false)
    render(<AcousticTwin analysis={demoAnalysis} selectedId={null} />)

    const table = screen.getByRole('table', { hidden: true })
    const bodyRows = within(table).getAllByRole('row', { hidden: true }).slice(1)
    expect(bodyRows).toHaveLength(demoAnalysis.frames.length)
    expect(bodyRows[0]).toHaveTextContent(demoAnalysis.frames[0].participantEnergy.toFixed(1))
  })

  it('shows the 3D scene when WebGL is available and lets the user switch to 2D', async () => {
    vi.mocked(webgl.detectWebGL).mockReturnValue(true)
    render(<AcousticTwin analysis={demoAnalysis} selectedId={null} />)

    expect(await screen.findByTestId('twin-scene-3d')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '3D view' })).toHaveAttribute('aria-pressed', 'true')

    await userEvent.click(screen.getByRole('button', { name: '2D view' }))

    expect(screen.getByRole('img', { name: /2D Acoustic Twin/ })).toBeInTheDocument()
    expect(screen.queryByTestId('twin-scene-3d')).not.toBeInTheDocument()
  })
})

describe('twin data mapping', () => {
  it('clamps energy to a visible 0..1 height', () => {
    expect(energyToUnit(-40)).toBe(0.03)
    expect(energyToUnit(40)).toBe(1)
    expect(energyToUnit(-5)).toBeCloseTo(0.5)
  })

  it('finds the flaw interval containing a time', () => {
    expect(findingAt(demoAnalysis.findings, 5)?.id).toBe('f-pace')
    expect(findingAt(demoAnalysis.findings, 1)).toBeUndefined()
  })
})
