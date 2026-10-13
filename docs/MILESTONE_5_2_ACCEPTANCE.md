# Milestone 5.2 acceptance checklist

The criteria were written before implementation from the milestone prompt. The results were filled in afterwards from the test and evaluation runs listed at the end.

Baseline before any change (commit `53b21ff`): backend 229 passed, frontend 66 passed, working tree clean. No test was failing beforehand.

## Results

| # | Criterion | Result | Evidence |
| --- | --- | --- | --- |
| B1 | The analysis service accepts participant audio, optional reference audio, optional participant and reference transcripts, and settings with defaults | PASS | `test_detection_api.py`: participant-only, with reference, with transcripts; `settings` echoed in the response |
| B2 | File type, size, duration, sample rate, channel count and unusable audio are validated with structured errors or explicit status, never a crash | PASS | `test_detection_api.py::test_invalid_uploads_return_structured_errors_for_participant_and_reference` (6 cases, both upload fields), `test_limits_on_size_duration_and_transcript_length`, `test_unusable_audio_is_reported_not_analysed_as_if_reliable`; `test_stress.py` |
| B3 | Transcript provenance is recorded as user-provided or machine-generated; human verification is never claimed | PASS | `test_the_api_never_reports_human_verification`, `test_a_user_transcript_is_recorded_as_user_provided_and_shared_with_the_reference` |
| C1 | Comparison uses word alignment to a shared transcript, never raw timestamps across recordings | PASS | `test_detection.py::test_pace_against_the_reference_is_measured_over_the_same_words`, `test_alignment_status_documents_window_strategy_and_normalisation` |
| C2 | Differing transcripts, missing alignment or an unsuitable reference withhold comparison findings and say why | PASS | `test_recordings_aligned_to_different_transcripts_are_not_compared`, `test_a_participant_who_said_something_else_fails_the_coverage_check`, `test_missing_alignment_on_either_side_makes_the_comparison_unavailable`, `test_an_unusable_reference_is_reported_and_not_compared`, and the API equivalents |
| C3 | Speech rate and pauses are compared over the aligned window | PASS | Pace and pause tests in `test_detection.py`; `test_pauses_do_not_count_as_slow_delivery` |
| C4 | Pitch is compared only over voiced frames, in semitones relative to each speaker | PASS | `test_unvoiced_frames_are_skipped_not_filled_in`, `test_pitch_height_alone_never_triggers_or_prevents_a_finding`, `test_narrow_pitch_variation_is_a_possible_finding_measured_in_semitones` |
| C5 | Energy, spectral and MFCC features are compared only when compatible | PASS | They are not compared at all, with the reason returned: `test_energy_spectral_and_mfcc_features_are_left_out_of_the_comparison_with_reasons` |
| C6 | Window, alignment strategy, normalisation, units and thresholds are in the response | PASS | `alignment_status`, each finding's `rule.thresholds` and `evidence[].unit`, and `settings`; `test_thresholds_are_configurable_and_reported` |
| D1 | Rushed and slow delivery rules | PASS | 6 parametrised pace cases; dataset: 9 of 9 rushed and 9 of 9 slow mild-to-severe samples reported, 0 of 6 near-reference |
| D2 | Excessive or irregular pause rules | PARTIAL | Excessive pauses: unit tests, and 9 of 9 dataset samples. There is no separate rule for irregular pause spacing; uneven pacing covers pace only |
| D3 | Filler-word rule, only from transcription | PARTIAL | Rule and tests work on recognised words (`test_recognised_fillers_are_reported_at_their_word_times` and three more). Never exercised on real audio containing fillers: the dataset has none, and recognisers often omit them |
| D4 | Uneven pacing rule | PASS | Unit tests; dataset: 6 of 6 moderate and severe samples, 0 of 3 mild. Thresholds were chosen on this dataset |
| D5 | Possible pitch monotony rule on valid voiced frames | PARTIAL | Unit tests pass. Dataset: 5 of 9 mild-to-severe samples; the other 4 belong to the low-voiced speaker and were withheld as unreliable, which is the intended behaviour but means the rule gives no answer for that voice. Threshold chosen on this dataset |
| D6 | Articulation or clarity only if a defensible measurement exists | PASS | No defensible measurement was found, so the rule reports `not_supported` with the reason: `test_articulation_is_never_reported_and_says_why` |
| D7 | Every finding has a stable ID, category, participant interval, evidence with values and units, reference values where valid, method, rule and threshold, evidence quality, limitations and an explanation | PASS | `test_every_finding_is_complete_and_stays_inside_the_recording`, `test_response_shape_is_stable_for_the_frontend` |
| D8 | Severity appears only where a documented, tested rule supports it | PASS | `test_severity_is_only_given_by_the_two_reference_based_magnitude_rules`; bands tested at 15%, 27% and 50% pace change and 0.6, 1.0 and 1.8 s extra pause. Severity is a magnitude band, not a perceptual rating, and says so |
| E1 | Unvoiced or invalid pitch frames cannot produce a finding | PASS | `test_too_few_voiced_frames_withholds_the_pitch_rule`, `test_octave_errors_inside_the_window_withhold_the_pitch_rule` |
| E2 | Pitch range is configurable; low, typical and high voices, octave errors, creaky and unvoiced regions are tested; low pitch is not simply discarded | PASS | `test_robustness.py`: 9 steady voices from 60 to 420 Hz, configurable range, weak-fundamental cases; `test_a_low_voice_is_measured_not_discarded`, `test_a_creaky_low_voice_is_flagged_unreliable_and_not_judged` |
| E3 | Unreliable pitch is marked low quality and pitch findings are withheld | PARTIAL | Works when the stability check fires. On the real low-voiced speaker it fired for 19 of 25 recordings; the other 6 are still treated as reliable |
| E4 | Clipping and other signal-quality checks are reused and lower evidence quality | PASS | `test_clipping_lowers_the_evidence_quality_of_every_finding`, API `test_clipped_audio_is_flagged_in_signal_quality` |
| E5 | Noisy pause detection is not presented as definitive | PASS | `test_a_pause_in_heavy_noise_is_only_a_possible_finding_with_no_severity` |
| F1 | Existing routes are reused; no redundant endpoint is added | PASS | `test_no_new_route_was_added_and_the_models_are_typed_in_openapi`: the six existing routes only |
| F2 | Typed models for status, signal quality, measurements, alignment status, findings, severity and limitations | PASS | Same test checks the OpenAPI schemas |
| F3 | Errors are safe: no credentials, file paths or stack traces | PASS | `test_a_processing_failure_returns_a_safe_error_without_internals` |
| F4 | The frontend distinguishes findings, no supported findings, partial analysis, invalid input and processing failure | PASS | `live.test.tsx` (findings, none, partial), `Workspace.test.tsx` (backend rejection, server failure, unreachable), Playwright upload flow |
| G1 | Comparable reference and participant recordings | PASS | `test_an_identically_paced_take_produces_no_findings_and_every_rule_reports_that_it_checked` |
| G2 | Faster and slower delivery | PASS | Pace tests |
| G3 | Longer pauses and irregular pacing | PASS | Pause and uneven-pacing tests |
| G4 | Supported filler-word detection | PASS | Filler tests (scripted recogniser output) |
| G5 | Missing reference audio | PASS | `test_without_a_reference_only_reference_free_rules_run` |
| G6 | Mismatched transcripts and failed alignment | PASS | See C2 |
| G7 | Low-pitch, creaky and unvoiced regions | PASS | See E1–E3 |
| G8 | Noise, clipping, silence, empty audio, short clips, unsupported formats | PASS | `test_unusable_audio_produces_no_findings_and_says_why`, noise and clipping tests, API invalid-upload tests |
| G9 | Missing features, invalid timestamps, insufficient evidence | PASS | `test_words_with_invalid_or_out_of_order_times_are_not_compared`, `test_too_few_comparable_words_is_insufficient_evidence`, `test_too_few_aligned_runs_withholds_uneven_pacing` |
| G10 | A valid no-finding result | PASS | G1 test and API `test_a_matching_take_against_a_reference_is_a_valid_no_finding_result` |
| G11 | API schema compatibility and error handling | PASS | See F1–F3 |
| G12 | Reproducibility across repeated runs | PASS | `test_results_are_identical_across_repeated_runs`, API `test_identical_requests_give_identical_responses` |
| H | Backend tests, frontend tests, dataset validation, end-to-end tests and frontend build all run | PASS | See "Runs" below |
| I | No secrets, env files or unauthorised audio staged; pushed to the intended remote and branch without force | PASS | Staged-file scan before the commit; no audio files changed |

## Runs

| Check | Result |
| --- | --- |
| Backend, `pytest` | 317 passed (88 new: 57 in `test_detection.py`, 21 in `test_detection_api.py`, 10 in `test_robustness.py`) |
| Frontend, `npm test` | 73 passed |
| Frontend end-to-end, `npm run test:e2e` | 7 passed, three consecutive cold runs |
| Frontend production build | succeeded |
| Dataset, `python -m app.dataset check` | passed: 0 errors, rebuilds identical |
| Dataset evaluation, `python -m app.detection.evaluate` (real `base` model) | Labelled flaw reported for 38 of 45 mild-to-severe samples; nothing reported for 3 references and 12 unclear-articulation samples; 5 findings of a category other than the label |
| Real browser run, real backend and model | A dataset reference and its severe-pause variant: 3 of 3 inserted pauses shown as findings, no console errors |

## Unresolved limitations

- Thresholds are project defaults. The uneven-pacing and pitch thresholds were chosen using the same demonstration dataset they are reported on, so those results are optimistic. Nothing has been validated with listeners or on natural flawed speech.
- Severity is a band of measured magnitude, not a rating of how a delivery sounds.
- No rule exists for irregular pause spacing, and none for articulation or clarity.
- The filler rule has not been run on real audio that contains fillers.
- Pitch findings are withheld for voices the tracker cannot follow stably, and the stability check does not catch every such recording.
- Word-level comparison depends on the speech recogniser. With the default `base` model, misrecognised words are simply left out of the comparison, which lowers coverage.
- The API cannot know whether a transcript was human-verified, so it never says one was.
- The frontend sends one transcript, used for both recordings; a separate reference transcript is supported by the API only.
- Coaching and reports for real recordings are still not implemented.

One test was changed for reasons unrelated to this milestone's behaviour: the end-to-end keyboard test pressed Tab before the page had rendered and failed on some cold starts. It now waits for the page first.
