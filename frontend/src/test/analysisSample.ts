// TEST MOCK of a backend /api/analyze response. Hand-written for tests; not produced by any real recording.

import type { AnalyzeResponse, ComponentStatus, Metric } from '../lib/api'

const metric = (status: Metric['status'], method: string, limitations: string[] = []): Metric => ({
  status,
  method,
  limitations,
})

const completed: ComponentStatus = { status: 'completed', code: null, message: null }

const DURATION = 4.8
const ENERGY = Array.from({ length: 48 }, (_, i) => (i >= 20 && i < 28 ? -70 : -20 + (i % 4)))
const PITCH = Array.from({ length: 48 }, (_, i) => (i >= 20 && i < 28 ? null : 150 + (i % 5)))

/** A new copy each time, so tests can modify it freely. */
export function sampleAnalysis(): AnalyzeResponse {
  return {
    is_demo: false,
    components: { features: completed, transcription: completed, alignment: completed },
    features: {
      is_demo: false,
      audio: {
        filename: 'talk.wav',
        duration_sec: DURATION,
        sample_rate_hz: 44100,
        channels: 1,
        analysis_sample_rate_hz: 16000,
        peak_amplitude: 0.5,
      },
      waveform: { ...metric('measured', 'Largest absolute sample amplitude per bucket.'), bucket_sec: 0.12, peaks: Array.from({ length: 40 }, (_, i) => (i % 5) / 10) },
      energy: {
        ...metric('measured', 'RMS amplitude in dBFS.', ['Levels depend on recording gain.']),
        series: { unit: 'dBFS', start_sec: 0, hop_sec: 0.1, values: ENERGY },
        mean_db: -27,
        max_db: -17,
        noise_floor_db: -70,
      },
      spectral: {
        ...metric('measured', 'Short-time Fourier transform.'),
        centroid: { unit: 'Hz', start_sec: 0, hop_sec: 0.1, values: ENERGY.map((v) => (v < -60 ? null : 900)) },
        mean_centroid_hz: 900,
      },
      mfcc: { ...metric('measured', '13 MFCCs.'), n_mfcc: 13, mean: new Array(13).fill(0), std: new Array(13).fill(1) },
      pitch: {
        ...metric('measured', 'Praat autocorrelation pitch tracking.', ['Octave errors are possible.']),
        series: { unit: 'Hz', start_sec: 0, hop_sec: 0.1, values: PITCH },
        voiced_fraction: 0.83,
        median_hz: 152,
        min_hz: 150,
        max_hz: 154,
        range_semitones: 0.4,
      },
      pauses: {
        ...metric('measured', 'Runs of quiet frames.', ['Detects silence only.']),
        threshold_db: -42,
        min_pause_sec: 0.25,
        intervals: [{ start: 2.0, end: 2.8, position: 'internal' }],
        internal_pause_count: 1,
        total_internal_pause_sec: 0.8,
        speech_sec: 4.0,
      },
      speaking_rate: {
        ...metric('estimated', 'Energy-peak syllable nuclei.', ['An estimate, not a count.']),
        syllable_nuclei: 16,
        speech_rate_syll_per_sec: 3.3,
        articulation_rate_syll_per_sec: 4.0,
      },
      transcript_rate: { ...metric('estimated', 'Transcript word count over duration.'), word_count: 5, words_per_minute: 62.5 },
      limitations: ['These are acoustic measurements of one recording.'],
    },
    transcription: {
      status: 'completed',
      text: 'good morning everyone thanks for coming',
      language: 'en',
      language_probability: 0.99,
      duration_sec: DURATION,
      engine: 'faster-whisper',
      model: 'base',
      segments: [{ start: 0.1, end: 4.4, text: 'good morning everyone thanks for coming' }],
      words: [
        { word: 'good', start: 0.1, end: 0.4, probability: 0.98 },
        { word: 'morning', start: 0.5, end: 0.9, probability: 0.97 },
        { word: 'everyone', start: 1.0, end: 1.6, probability: 0.95 },
        { word: 'thanks', start: 2.9, end: 3.3, probability: 0.9 },
        { word: 'for', start: 3.4, end: 3.6, probability: 0.99 },
        { word: 'coming', start: 3.7, end: 4.4, probability: 0.96 },
      ],
      word_timestamps: 'available',
      limitations: ['The text is the model’s best guess.'],
    },
    alignment: {
      status: 'partial',
      transcript_source: 'supplied',
      method: 'Transcript-to-recognition alignment.',
      word_count: 6,
      aligned_count: 4,
      substituted_count: 1,
      unaligned_count: 1,
      coverage: 0.667,
      words: [
        { index: 0, word: 'Good', status: 'aligned', start: 0.1, end: 0.4, recognized_as: null, probability: 0.98 },
        { index: 1, word: 'morning', status: 'aligned', start: 0.5, end: 0.9, recognized_as: null, probability: 0.97 },
        { index: 2, word: 'everyone.', status: 'aligned', start: 1.0, end: 1.6, recognized_as: null, probability: 0.95 },
        { index: 3, word: 'Thank', status: 'substituted', start: 2.9, end: 3.3, recognized_as: 'thanks', probability: 0.9 },
        { index: 4, word: 'you', status: 'unaligned', start: null, end: null, recognized_as: null, probability: null },
        { index: 5, word: 'coming', status: 'aligned', start: 3.7, end: 4.4, recognized_as: null, probability: 0.96 },
      ],
      unmatched_recognized: [{ word: 'for', start: 3.4, end: 3.6, probability: 0.99 }],
      limitations: ['Timing accuracy is that of the recogniser.'],
    },
    limitations: ['No comparison with a baseline delivery and no flaw detection is performed yet.'],
  }
}

/** Minimal stand-in for a fetch Response. */
export function jsonResponse(body: unknown, status = 200): Response {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response
}
