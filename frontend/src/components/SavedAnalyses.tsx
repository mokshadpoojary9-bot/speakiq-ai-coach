import { useId, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, deleteAnalysis, openAnalysis, saveAnalysis, type AnalyzeResponse, type SavedAnalysis } from '../lib/api'
import { useAnalysisSession } from '../lib/session'
import { btnPrimary, btnSecondary, ErrorState } from './ui'

function messageOf(error: unknown): string {
  if (error instanceof ApiError) {
    return error.kind === 'network' ? 'The backend could not be reached.' : error.message
  }
  return 'Something unexpected went wrong.'
}

/** Optional saving of a real analysis. Nothing is sent until the button is pressed. */
export function SavePanel({ result }: { result: AnalyzeResponse }) {
  const [state, setState] = useState<
    { kind: 'idle' } | { kind: 'saving' } | { kind: 'saved'; saved: SavedAnalysis } | { kind: 'deleted' } | { kind: 'error'; message: string }
  >({ kind: 'idle' })

  async function save() {
    setState({ kind: 'saving' })
    try {
      setState({ kind: 'saved', saved: await saveAnalysis(result) })
    } catch (error) {
      setState({ kind: 'error', message: messageOf(error) })
    }
  }

  async function remove(saved: SavedAnalysis) {
    try {
      await deleteAnalysis(saved.id, saved.access_key)
      setState({ kind: 'deleted' })
    } catch (error) {
      setState({ kind: 'error', message: messageOf(error) })
    }
  }

  return (
    <div className="flex flex-col gap-3 text-sm">
      <p className="text-muted">
        Saves these results, including the transcript text, to this backend’s database so you can open them later. The
        audio is never saved. You get an ID and an access key; both are needed to open or delete it.
      </p>
      {state.kind === 'saved' ? (
        <div role="status" className="rounded-lg border border-accent/40 bg-accent/5 p-4">
          <p className="font-semibold text-accent">Saved.</p>
          <p className="mt-1 text-warn">Copy both values now. The access key is shown only once and cannot be recovered.</p>
          <dl className="mt-3 grid gap-2 font-mono text-xs">
            <div>
              <dt className="font-sans text-muted">ID</dt>
              <dd className="break-all">{state.saved.id}</dd>
            </div>
            <div>
              <dt className="font-sans text-muted">Access key</dt>
              <dd className="break-all">{state.saved.access_key}</dd>
            </div>
          </dl>
          <button type="button" className={`${btnSecondary} mt-3`} onClick={() => void remove(state.saved)}>
            Delete the saved copy
          </button>
        </div>
      ) : state.kind === 'deleted' ? (
        <p role="status" className="text-muted">
          The saved copy was deleted.
        </p>
      ) : (
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" className={btnSecondary} disabled={state.kind === 'saving'} onClick={() => void save()}>
            {state.kind === 'saving' ? 'Saving…' : 'Save this analysis'}
          </button>
        </div>
      )}
      {state.kind === 'error' && <ErrorState title="Not saved" message={state.message} />}
    </div>
  )
}

/** Open, or delete, an analysis saved earlier, by its ID and access key. */
export function OpenSavedForm() {
  const idField = useId()
  const keyField = useId()
  const { setSession } = useAnalysisSession()
  const [id, setId] = useState('')
  const [key, setKey] = useState('')
  const [state, setState] = useState<{ kind: 'idle' | 'busy' | 'opened' | 'deleted' } | { kind: 'error'; message: string }>({ kind: 'idle' })
  const ready = id.trim() !== '' && key.trim() !== '' && state.kind !== 'busy'

  async function open(event: FormEvent) {
    event.preventDefault()
    setState({ kind: 'busy' })
    try {
      const stored = await openAnalysis(id.trim(), key.trim())
      // There is no audio in a saved analysis, so playback is unavailable for it.
      setSession({ result: stored.result, file: null, analysedAt: new Date(stored.created_at) })
      setState({ kind: 'opened' })
    } catch (error) {
      setState({ kind: 'error', message: messageOf(error) })
    }
  }

  async function remove() {
    setState({ kind: 'busy' })
    try {
      await deleteAnalysis(id.trim(), key.trim())
      setState({ kind: 'deleted' })
    } catch (error) {
      setState({ kind: 'error', message: messageOf(error) })
    }
  }

  return (
    <form onSubmit={(event) => void open(event)} aria-label="Open a saved analysis" className="flex flex-col gap-3 text-sm">
      <div className="grid gap-3 sm:grid-cols-2">
        <label htmlFor={idField} className="text-muted">
          ID
          <input
            id={idField}
            value={id}
            onChange={(event) => setId(event.target.value)}
            autoComplete="off"
            className="mt-1 block w-full rounded-lg border border-line bg-ink-900 p-2 font-mono text-xs text-fg"
          />
        </label>
        <label htmlFor={keyField} className="text-muted">
          Access key
          <input
            id={keyField}
            type="password"
            value={key}
            onChange={(event) => setKey(event.target.value)}
            autoComplete="off"
            className="mt-1 block w-full rounded-lg border border-line bg-ink-900 p-2 font-mono text-xs text-fg"
          />
        </label>
      </div>
      <div className="flex flex-wrap gap-3">
        <button type="submit" className={btnPrimary} disabled={!ready}>
          Open
        </button>
        <button type="button" className={btnSecondary} disabled={!ready} onClick={() => void remove()}>
          Delete it
        </button>
      </div>
      {state.kind === 'opened' && (
        <p role="status">
          Opened. <Link to="/dashboard" className="font-medium text-accent underline underline-offset-2">View it on the dashboard</Link>. Playback is not available because audio is never saved.
        </p>
      )}
      {state.kind === 'deleted' && <p role="status">The saved analysis was deleted.</p>}
      {state.kind === 'error' && <ErrorState title="That did not work" message={state.message} />}
    </form>
  )
}
