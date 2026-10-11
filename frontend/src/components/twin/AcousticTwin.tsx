import { lazy, Suspense, useState } from 'react'
import { detectWebGL } from '../../lib/webgl'
import { ErrorBoundary } from '../ErrorBoundary'
import { LoadingState } from '../ui'
import { TwinFallback2D } from './TwinFallback2D'
import { twinLegend, type TwinProps } from './twinData'

const TwinScene = lazy(() => import('./TwinScene'))

type Mode = '3d' | '2d'

const toggleClass = (active: boolean) =>
  `rounded-md px-3 py-1.5 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
    active ? 'bg-ink-700 text-accent' : 'text-muted hover:text-fg'
  }`

/** Shows the 3D scene when WebGL works and the 2D view otherwise, or on request. */
export function AcousticTwin({ analysis, selectedId }: TwinProps) {
  const [webglAvailable, setWebglAvailable] = useState(detectWebGL)
  const [mode, setMode] = useState<Mode>(webglAvailable ? '3d' : '2d')
  const [sceneFailed, setSceneFailed] = useState(false)

  const show3d = mode === '3d' && webglAvailable

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div role="group" aria-label="Visualization mode" className="inline-flex rounded-lg border border-line bg-ink-900 p-1">
          <button
            type="button"
            className={toggleClass(show3d)}
            aria-pressed={show3d}
            disabled={!webglAvailable}
            onClick={() => setMode('3d')}
          >
            3D view
          </button>
          <button type="button" className={toggleClass(!show3d)} aria-pressed={!show3d} onClick={() => setMode('2d')}>
            2D view
          </button>
        </div>
        {!webglAvailable && (
          <p role="status" className="text-sm text-warn">
            {sceneFailed
              ? 'The 3D view failed to start, so the 2D view is shown instead.'
              : 'WebGL is not available in this browser, so the 2D view is shown instead.'}
          </p>
        )}
      </div>

      {show3d ? (
        <ErrorBoundary
          // Rendering failed after detection passed (for example a lost context): drop to 2D.
          onError={() => {
            setSceneFailed(true)
            setWebglAvailable(false)
          }}
          fallback={<TwinFallback2D analysis={analysis} selectedId={selectedId} />}
        >
          <Suspense fallback={<LoadingState label="Loading 3D view…" />}>
            <div
              className="h-[340px] overflow-hidden rounded-lg border border-line sm:h-[460px]"
              role="img"
              aria-label="3D Acoustic Twin. Bar height shows relative energy over time; the front row is the participant and the back row is the baseline. Switch to the 2D view for a data table."
            >
              <TwinScene analysis={analysis} selectedId={selectedId} />
            </div>
            <p className="mt-2 text-xs text-muted">Drag to orbit, scroll to zoom. The view only moves when you move it.</p>
          </Suspense>
        </ErrorBoundary>
      ) : (
        <TwinFallback2D analysis={analysis} selectedId={selectedId} />
      )}

      <ul className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-xs text-muted" aria-label="Legend">
        {twinLegend.map((item) => (
          <li key={item.label} className="inline-flex items-center gap-2">
            <span aria-hidden="true" className="h-2.5 w-2.5 rounded-sm" style={{ background: item.color }} />
            {item.label}
          </li>
        ))}
      </ul>
    </div>
  )
}
