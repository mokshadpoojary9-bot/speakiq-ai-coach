// TEST MOCK of a backend /api/analyze response. Hand-written for tests; not produced by any real recording.

import type { AnalyzeResponse, ComponentStatus, FindingCategory, Metric, RuleReport } from '../lib/api'

const metric = (status: Metric['status'], method: string, limitations: string[] = []): Metric => ({
  status,
  method,
  limitations,
})

const completed: ComponentStatus = { status: 'completed', code: null, message: null }

const checked = (rule_id: string, category: FindingCategory, status: RuleReport['status'] = 'not_triggered', reason = ''): RuleReport => ({
  rule_id,
  category,
  status,
  reason,
  findings: status === 'triggered' ? 1 : 0,
  measured: {},
  thresholds: {},
})

const DURATION = 4.8
const ENERGY = Array.from({ length: 48 }, (_, i) => (i >= 20 && i < 28 ? -70 : -20 + (i % 4)))
const PITCH = Array.from({ length: 48 }, (_, i) => (i >= 20 && i < 28 ? null : 150 + (i % 5)))

/** A new copy each time, so tests can modify it freely. */
export function sampleAnalysis(): AnalyzeResponse {
  return {
    is_demo: false,
    status: 'completed',
    components: { features: completed, transcription: completed, alignment: completed },
    signal_quality: { usable: true, issues: [] },
    transcripts: {
      participant: { source: 'user_provided', review_status: 'not_reviewed', human_verified: false, text: 'Good morning everyone. Thank you coming' },
      reference: { source: 'machine_generated', review_status: 'not_reviewed', human_verified: false, text: 'good morning everyone thank you coming' },
      shared_for_comparison: {
        source: 'user_provided',
        review_status: 'not_reviewed',
        human_verified: false,
        text: 'Good morning everyone. Thank you coming',
        origin: 'participant_transcript',
      },
    },
    reference: { filename: 'reference.wav', duration_sec: 4.1, signal_quality: { usable: true, issues: [] } },
    alignment_status: {
      status: 'aligned',
      reason: '',
      strategy: 'Both recordings are aligned to one shared transcript.',
      transcript_source: 'user_provided',
      transcript_word_count: 6,
      words_compared: 5,
      words_excluded: { not_recognised_in_participant: 1 },
      participant_window: { start: 0.1, end: 4.4 },
      reference_window: { start: 0.1, end: 3.7 },
      normalization: 'Pitch is converted to semitones relative to each speaker.',
    },
    findings: [
      {
        id: 'pause_vs_reference:2000-2800',
        category: 'excessive_pause',
        title: 'Longer pause than the reference',
        start: 2.0,
        end: 2.8,
        reference_interval: { start: 1.0, end: 1.9 },
        evidence: [
          { feature: 'silence_between_the_same_words', unit: 's', participant_value: 0.8, reference_value: 0.1, difference: 0.7, ratio: 8 },
        ],
        comparison_method: 'Measured silence between the same words in both recordings.',
        rule: { rule_id: 'pause_vs_reference', description: 'Flag a pause longer than the reference by more than the threshold.', thresholds: { pause_excess_sec: 0.4 } },
        evidence_quality: 'high',
        severity: 'minor',
        severity_basis: 'Extra silence beyond the reference (0.70 s): minor below 0.8 s.',
        explanation: 'There are 0.80 s of silence after ‘everyone.’, where the reference has 0.10 s.',
        limitations: ['A longer pause can be deliberate.'],
      },
    ],
    coaching: [
      {
        id: 'tip:pause_vs_reference:excessive_pause',
        category: 'excessive_pause',
        finding_ids: ['pause_vs_reference:2000-2800'],
        action: 'Shorten the pauses at the marked points, unless you meant them.',
        practice: 'Rehearse the phrase on either side of each marked pause as one unit, then re-record.',
        based_on: 'There are 0.80 s of silence after ‘everyone.’, where the reference has 0.10 s.',
        caution: null,
        certainty: 'confirmed',
        reason: 'The measured silence at these points was longer than the reference’s silence at the same words by more than the rule’s threshold.',
        evidence: [
          {
            finding_id: 'pause_vs_reference:2000-2800',
            start: 2.0,
            end: 2.8,
            feature: 'silence_between_the_same_words',
            unit: 's',
            participant_value: 0.8,
            reference_value: 0.1,
            difference: 0.7,
            evidence_quality: 'high',
          },
        ],
        source: 'rule_based',
      },
    ],
    clarity: {
      status: 'estimated',
      participant: { articulation_rate_syll_per_sec: 4.12, mean_word_confidence: 0.83, low_confidence_word_share: 0.167, words: 6 },
      reference: { articulation_rate_syll_per_sec: 3.6, mean_word_confidence: 0.9, low_confidence_word_share: 0, words: 6 },
      method: 'Articulation rate is the number of syllable nuclei divided by the speaking time with pauses removed.',
      limitations: ['This is an estimate, not a measure of how clearly someone speaks.'],
    },
    rules: [
      checked('pace_vs_reference', 'rushed_delivery'),
      checked('pace_vs_reference', 'slow_delivery'),
      checked('pause_vs_reference', 'excessive_pause', 'triggered'),
      checked('pause_placement_vs_reference', 'irregular_pauses'),
      checked('pacing_vs_reference', 'uneven_pacing', 'withheld', 'Needs at least 3 runs of 5 consecutive aligned words; found 1.'),
      checked('filler_lexicon', 'filler_word', 'not_triggered', 'None were recognised. Speech recognisers often leave fillers out.'),
      checked('pitch_range_vs_reference', 'pitch_monotony'),
      checked('articulation', 'unclear_articulation', 'not_supported', 'No finding is made.'),
    ],
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
      clipping: { ...metric('measured', 'Counts flat-topped peaks.'), verdict: 'not_detected', peak_amplitude: 0.5, flat_top_runs: 0 },
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
        reliability: 'ok',
      },
      pauses: {
        ...metric('measured', 'Runs of quiet frames.', ['Detects silence only.']),
        threshold_db: -42,
        min_pause_sec: 0.25,
        intervals: [{ start: 2.0, end: 2.8, position: 'internal' }],
        reliability: 'ok',
        threshold_rule: 'relative_to_speech',
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
    limitations: ['Findings are measured differences that crossed a documented threshold.'],
  }
}

/** Minimal stand-in for a fetch Response. */
export function jsonResponse(body: unknown, status = 200): Response {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response
}
