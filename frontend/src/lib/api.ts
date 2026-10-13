// Client for the FastAPI backend. Types mirror backend/app/**/schemas.py. All times are in seconds.

// Set VITE_API_BASE_URL in frontend/.env.local (development) or the host's build settings (deployment).
export const API_BASE_URL: string = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')

export type MetricStatus = 'measured' | 'estimated' | 'unavailable'
/** 'low' means the backend saw signs that the measurement is unreliable for this recording. */
export type Reliability = 'ok' | 'low'

export interface Metric {
  status: MetricStatus
  method: string
  limitations: string[]
}

/** Value i is at `start_sec + i * hop_sec`; null means no value at that frame. */
export interface FrameSeries {
  unit: string
  start_sec: number
  hop_sec: number
  values: (number | null)[]
}

export interface PauseInterval {
  start: number
  end: number
  position: 'leading' | 'internal' | 'trailing'
}

export interface AudioFeatures {
  is_demo: false
  audio: {
    filename: string
    duration_sec: number
    sample_rate_hz: number
    channels: number
    analysis_sample_rate_hz: number
    peak_amplitude: number
  }
  waveform: Metric & { bucket_sec: number; peaks: number[] }
  /** Absent in responses from backends older than the clipping check. */
  clipping?: Metric & {
    verdict: 'detected' | 'not_detected' | 'uncertain' | null
    peak_amplitude: number | null
    flat_top_runs: number | null
  }
  energy: Metric & {
    series: FrameSeries | null
    mean_db: number | null
    max_db: number | null
    noise_floor_db: number | null
  }
  spectral: Metric & { centroid: FrameSeries | null; mean_centroid_hz: number | null }
  mfcc: Metric & { n_mfcc: number; mean: number[]; std: number[] }
  pitch: Metric & {
    series: FrameSeries | null
    voiced_fraction: number | null
    median_hz: number | null
    min_hz: number | null
    max_hz: number | null
    range_semitones: number | null
    reliability?: Reliability | null
  }
  pauses: Metric & {
    threshold_db: number | null
    min_pause_sec: number
    intervals: PauseInterval[]
    reliability?: Reliability | null
    threshold_rule?: 'relative_to_speech' | 'noise_floor' | null
    internal_pause_count: number | null
    total_internal_pause_sec: number | null
    speech_sec: number | null
  }
  speaking_rate: Metric & {
    syllable_nuclei: number | null
    speech_rate_syll_per_sec: number | null
    articulation_rate_syll_per_sec: number | null
  }
  transcript_rate: Metric & { word_count: number | null; words_per_minute: number | null }
  limitations: string[]
}

export interface RecognizedWord {
  word: string
  start: number
  end: number
  probability: number | null
}

export interface Transcription {
  status: 'completed' | 'no_speech'
  text: string
  language: string | null
  language_probability: number | null
  duration_sec: number
  engine: string
  model: string
  segments: { start: number; end: number; text: string }[]
  words: RecognizedWord[]
  word_timestamps: 'available' | 'unavailable'
  limitations: string[]
}

export type WordAlignmentStatus = 'aligned' | 'substituted' | 'unaligned'

export interface AlignedWord {
  index: number
  word: string
  status: WordAlignmentStatus
  start: number | null
  end: number | null
  recognized_as: string | null
  probability: number | null
}

export interface Alignment {
  status: 'aligned' | 'partial' | 'failed'
  transcript_source: 'supplied' | 'transcribed'
  method: string
  word_count: number
  aligned_count: number
  substituted_count: number
  unaligned_count: number
  coverage: number
  words: AlignedWord[]
  unmatched_recognized: RecognizedWord[]
  limitations: string[]
}

export interface ComponentStatus {
  status: 'completed' | 'unavailable' | 'failed'
  code: string | null
  message: string | null
}

export type FindingCategory =
  | 'rushed_delivery'
  | 'slow_delivery'
  | 'excessive_pause'
  | 'irregular_pauses'
  | 'filler_word'
  | 'uneven_pacing'
  | 'pitch_monotony'
  | 'unclear_articulation'

export interface TimeSpan {
  start: number
  end: number
}

export interface FindingEvidence {
  feature: string
  unit: string
  participant_value: number | null
  reference_value: number | null
  difference: number | null
  ratio: number | null
}

/** A measured difference that crossed a documented threshold. Named to avoid the demo fixture's `Finding`. */
export interface DetectedFinding {
  id: string
  category: FindingCategory
  title: string
  /** In the participant recording. */
  start: number
  end: number
  reference_interval: TimeSpan | null
  evidence: FindingEvidence[]
  comparison_method: string
  rule: { rule_id: string; description: string; thresholds: Record<string, number | string> }
  evidence_quality: 'high' | 'moderate' | 'low'
  /** A magnitude band of the measured difference; null when no tested rule supports one. */
  severity: 'minor' | 'moderate' | 'major' | null
  severity_basis: string | null
  explanation: string
  limitations: string[]
}

export interface RuleReport {
  rule_id: string
  category: FindingCategory
  status: 'triggered' | 'not_triggered' | 'withheld' | 'not_supported'
  reason: string
  findings: number
  measured: Record<string, number | null>
  thresholds: Record<string, number | string>
}

export interface SignalQuality {
  usable: boolean
  issues: { code: string; level: 'blocking' | 'warning'; message: string; affects: string[] }[]
}

export interface AlignmentStatus {
  status: 'aligned' | 'unavailable' | 'no_reference'
  reason: string
  strategy: string
  transcript_source: 'user_provided' | 'machine_generated' | 'none'
  transcript_word_count: number
  words_compared: number
  /** Transcript words left out of the comparison, counted by reason. */
  words_excluded?: Record<string, number>
  /** Words heard in each recording that are not in the shared transcript; never compared. */
  unmatched_recognised?: { participant?: number; reference?: number }
  participant_window: TimeSpan | null
  reference_window: TimeSpan | null
  normalization: string
}

export interface TranscriptInfo {
  source: 'user_provided' | 'machine_generated' | 'none'
  /** user_attested: the sender stated they checked their transcript. The API cannot verify that. */
  review_status: 'not_reviewed' | 'user_attested'
  /** The API has no evidence of human review and never reports any. */
  human_verified: false
  text: string | null
  /** Only on the shared transcript: which text both recordings were aligned to. */
  origin?: 'participant_transcript' | 'reference_transcript' | 'reference_recognition'
  /** Only on the shared transcript: which recordings the sender said they checked it against. */
  attested_for?: ('participant' | 'reference')[]
}

/** Fixed, rule-based wording built from findings. No language model. */
export interface CoachingTip {
  id: string
  category: FindingCategory
  finding_ids: string[]
  action: string
  practice: string
  based_on: string
  caution: string | null
  source: string
}

export interface AnalyzeResponse {
  is_demo: false
  /** completed: findings. completed_no_findings: checked, nothing over threshold. partial: something could not run. */
  status: 'completed' | 'completed_no_findings' | 'partial'
  components: { features: ComponentStatus; transcription: ComponentStatus; alignment: ComponentStatus }
  signal_quality: SignalQuality
  features: AudioFeatures
  transcription: Transcription | null
  alignment: Alignment | null
  transcripts: { participant: TranscriptInfo; reference: TranscriptInfo | null; shared_for_comparison: TranscriptInfo | null }
  reference: { filename: string; duration_sec: number; signal_quality: SignalQuality } | null
  alignment_status: AlignmentStatus
  findings: DetectedFinding[]
  rules: RuleReport[]
  /** Absent in responses from backends older than rule-based coaching. */
  coaching?: CoachingTip[]
  limitations: string[]
}

export interface HealthResponse {
  status: 'ok'
  service: string
  version: string
  environment: string
}

/**
 * network: no response at all (backend down, wrong URL, or blocked by CORS).
 * http: the backend answered with an error. invalid_response: the answer was not what the API promises.
 */
export type ApiErrorKind = 'network' | 'http' | 'invalid_response'

export class ApiError extends Error {
  readonly kind: ApiErrorKind
  readonly status: number | null
  readonly code: string | null

  constructor(kind: ApiErrorKind, message: string, status: number | null = null, code: string | null = null) {
    super(message)
    this.name = 'ApiError'
    this.kind = kind
    this.status = status
    this.code = code
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, init)
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError('network', `No response from the backend at ${API_BASE_URL}.`)
  }

  let body: unknown
  try {
    body = await response.json()
  } catch {
    throw new ApiError('invalid_response', `The backend returned an unreadable response (HTTP ${response.status}).`, response.status)
  }

  if (!response.ok) {
    const detail = (body as { detail?: { code?: unknown; message?: unknown } } | null)?.detail
    const message = typeof detail?.message === 'string' ? detail.message : `The backend returned HTTP ${response.status}.`
    const code = typeof detail?.code === 'string' ? detail.code : null
    throw new ApiError('http', message, response.status, code)
  }
  return body as T
}

export function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return request<HealthResponse>('/api/health', { signal })
}

/**
 * Measures the recording, transcribes and aligns it, and applies the delivery rules. With a
 * `reference` recording of the same text, the rules compare the two over the words recognised in both.
 */
export async function analyzeRecording(
  file: File,
  transcript: string,
  signal?: AbortSignal,
  reference?: File | null,
  transcriptReviewed = false,
): Promise<AnalyzeResponse> {
  const form = new FormData()
  form.append('file', file, file.name)
  if (reference) form.append('reference', reference, reference.name)
  if (transcript.trim()) {
    form.append('transcript', transcript)
    // A statement by the user, recorded as such. It only applies to text they supplied.
    if (transcriptReviewed) form.append('transcript_reviewed', 'true')
  }

  const result = await request<AnalyzeResponse>('/api/analyze', { method: 'POST', body: form, signal })
  if (!result || typeof result !== 'object' || !result.features || !result.components || !Array.isArray(result.findings)) {
    throw new ApiError('invalid_response', 'The backend response did not contain an analysis.')
  }
  return result
}
