import { afterEach, describe, expect, it, vi } from 'vitest'
import { jsonResponse, sampleAnalysis } from '../test/analysisSample'
import { analyzeRecording, API_BASE_URL, ApiError, fetchHealth } from './api'

const file = new File([new Uint8Array(16)], 'talk.wav', { type: 'audio/wav' })

afterEach(() => {
  vi.mocked(fetch).mockReset()
  vi.mocked(fetch).mockRejectedValue(new TypeError('no backend in tests'))
})

async function failure(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise
  } catch (error) {
    return error as ApiError
  }
  throw new Error('expected the call to fail')
}

describe('API client', () => {
  it('uses the configured base URL and the /api routes', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ status: 'ok', service: 's', version: '0.1.0', environment: 'test' }))

    await fetchHealth()

    expect(API_BASE_URL).not.toMatch(/\/$/)
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe(`${API_BASE_URL}/api/health`)
  })

  it('returns the analysis on success', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(sampleAnalysis()))

    const result = await analyzeRecording(file, '  ')

    expect(result.features.audio.filename).toBe('talk.wav')
    expect((vi.mocked(fetch).mock.calls[0][1]?.body as FormData).has('transcript')).toBe(false)
  })

  it('classifies a failed connection as a network error', async () => {
    vi.mocked(fetch).mockRejectedValue(new TypeError('Failed to fetch'))

    const error = await failure(analyzeRecording(file, ''))

    expect(error).toBeInstanceOf(ApiError)
    expect(error.kind).toBe('network')
    expect(error.message).toContain(API_BASE_URL)
  })

  it('passes on the backend’s error code and message', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ detail: { code: 'unsupported_audio', message: 'Unsupported file type.' } }, 415))

    const error = await failure(analyzeRecording(file, ''))

    expect([error.kind, error.status, error.code, error.message]).toEqual(['http', 415, 'unsupported_audio', 'Unsupported file type.'])
  })

  it('copes with error bodies that are not in the expected shape', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ detail: 'plain string' }, 500))

    const error = await failure(analyzeRecording(file, ''))

    expect([error.kind, error.status, error.code]).toEqual(['http', 500, null])
    expect(error.message).toBe('The backend returned HTTP 500.')
  })

  it('rejects a success response that is not an analysis', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ hello: 'world' }))

    expect((await failure(analyzeRecording(file, ''))).kind).toBe('invalid_response')
  })

  it('lets an abort propagate so callers can tell a cancel from a failure', async () => {
    vi.mocked(fetch).mockRejectedValue(new DOMException('Aborted', 'AbortError'))

    const error = await failure(analyzeRecording(file, ''))

    expect(error).not.toBeInstanceOf(ApiError)
    expect((error as unknown as DOMException).name).toBe('AbortError')
  })
})
