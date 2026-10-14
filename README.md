# SpeakIQ AI Coach

Evidence-first speech delivery analysis with temporally grounded explanations, built for the track **Contrastive Speech Analytics & Temporal Flaw Grounding**.

The full specification lives in [`docs/PROJECT_SPEC.yaml`](docs/PROJECT_SPEC.yaml) and is the source of truth for every milestone.

## Status

| Area | State |
| --- | --- |
| Backend API: health, acoustic features, transcription, word alignment, combined analysis | Working (see [API](#api)) |
| Findings with intervals and evidence for pace, pauses, pause placement, fillers, uneven pacing and pitch variation (`POST /api/analyze`, optional reference recording) | Working; shown on the dashboard. See [Findings](#findings-apianalyze) |
| Rule-based suggestions and a printable report for your recording | Working on the Evidence Coach and Reports pages. Fixed wording built from the findings; no language model |
| Raw comparison of two recordings (`POST /api/compare`) | Working for measured differences only; the frontend uses `/api/analyze` instead |
| Recording-quality checks: clipping, pitch-tracking reliability, noisy-pause confidence | Working; shown on the dashboard |
| Local transcription with faster-whisper | Working; no Hugging Face token needed for the default model |
| Frontend pages: landing, workspace, dashboard, Acoustic Twin, Evidence Coach, reports | Working |
| Audio file validation, playback and waveform in the workspace | Working, in the browser only |
| Workspace → backend: upload a recording and an optional reference, get real measurements, transcript, word timing and findings | Working (`POST /api/analyze`) |
| Dashboard and Acoustic Twin for your recording | Working with real backend results; switchable to the demo fixture |
| Demo dashboard, coaching and report content | **Demo fixture** (`frontend/src/fixtures/demoAnalysis.ts`), not computed from audio. Shown before you analyse a recording, or when you switch to it |
| Contrastive demonstration dataset: 3 real recordings, 84 transformed variants (filler sounds synthetic), schema, validator, review tool, dataset card | Built and validated (see [Dataset](#dataset)) |
| Articulation or clarity findings | Deliberately not supported: no measurement was found that would not penalise accent, voice or microphone |
| Free-form coaching questions, language-model coaching | Not implemented |
| Dataset publication | Not published; export and upload guide in `data/HOSTING.md` |
| Optional saving of analysis results to Supabase | Implemented; off until you configure it. See [Saving analyses](#saving-analyses-optional) |
| Hosting (Render backend, Vercel frontend) | **Not deployed.** Configuration prepared in `render.yaml` and `frontend/vercel.json`; steps in [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) |

Every frontend view that shows fixture data carries a "Demo data — not a real analysis" label, and views of your own recording carry a "Real analysis" label. A real analysis is kept in browser memory and is lost when the page is reloaded, unless you save it (optional, see [Saving analyses](#saving-analyses-optional)). No paid API keys are needed to run the project locally.

## Repository layout

```
frontend/   React + Vite + TypeScript + Tailwind CSS
backend/    Python + FastAPI
  app/audio/    acoustic feature extraction
  app/speech/   transcription and word alignment
  app/comparison/ reference-versus-participant differences
  app/detection/  signal quality, alignment status, rule-based findings and coaching
  app/persistence.py  optional Supabase storage of analysis results
  app/dataset/  dataset schema, transforms, build, validation, review and export
data/       contrastive dataset: sources, examples, manifest, schema, dataset card
docs/       Project specification, deployment guide, Supabase schema, final audit
```

## Prerequisites

- Node.js 20 or newer (developed on 24) and npm
- Python 3.11 or newer (developed on 3.14)
- About 150 MB of disk space and an internet connection for the one-time transcription model download

## Backend

From `backend/` (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
```

On macOS or Linux, activate with `source .venv/bin/activate` instead.

- Health check: http://127.0.0.1:8000/api/health
- Interactive API docs (Swagger UI): http://127.0.0.1:8000/docs
- OpenAPI schema: http://127.0.0.1:8000/openapi.json
- Tests: `pytest` (mocked; no internet, token or model download needed)

### Model setup

Transcription runs locally with [faster-whisper](https://github.com/SYSTRAN/faster-whisper). The default model is `base` (about 145 MB), a public model that downloads **without a Hugging Face token**. It is fetched automatically on the first transcription request, which makes that request slow. To download it ahead of time:

```powershell
python -m app.speech.prefetch
```

Larger models (`small`, `medium`, `large-v3`) are more accurate and slower; set `WHISPER_MODEL` to change it.

### Backend environment variables

All optional. Copy `backend/.env.example` to `backend/.env` to change them. `backend/.env` is ignored by Git.

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_ENV` | `development` | Reported by `/api/health` |
| `BACKEND_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Browser origins allowed to call the API |
| `MAX_UPLOAD_MB` | `25` | Largest accepted upload |
| `MAX_AUDIO_SECONDS` | `300` | Longest accepted recording |
| `PAUSE_SILENCE_BELOW_SPEECH_DB` | `25` | In quiet recordings, how far below the speech level counts as silence |
| `PAUSE_NOISE_MARGIN_DB` | `3` | In noisy recordings, how close to the noise floor counts as silence |
| `PAUSE_MIN_SEC` | `0.25` | Shortest silence reported as a pause |
| `PITCH_MIN_HZ`, `PITCH_MAX_HZ` | `50`, `600` | Widest pitch range the tracker may search |
| `WHISPER_MODEL` | `base` | faster-whisper model name or Hugging Face repository |
| `WHISPER_DEVICE` | `cpu` | `cpu` or `cuda` |
| `WHISPER_COMPUTE_TYPE` | `int8` | For example `int8`, `float32` |
| `WHISPER_LANGUAGE` | empty (auto-detect) | Force a language code such as `en` |
| `WHISPER_DOWNLOAD_ROOT` | empty (Hugging Face cache) | Where to store the model |
| `HF_TOKEN` | empty | **Secret.** Only needed if `WHISPER_MODEL` points at a private or gated repository |
| `SUPABASE_URL` | empty | Optional. Your Supabase project URL; saving is off while empty |
| `SUPABASE_SERVICE_ROLE_KEY` | empty | **Secret, optional.** Backend only; full database access. Saving is off while empty |
| `SUPABASE_TABLE` | `analyses` | Table created by `docs/supabase/schema.sql` |
| `MAX_SAVED_RESULT_MB` | `5` | Largest analysis result accepted for saving |

`HF_TOKEN` is read only by the backend, is never returned by the API (`/api/health` reports only whether one is configured) and must never be put in the frontend.

## Frontend

From `frontend/`:

```powershell
npm install
Copy-Item .env.example .env.local
npm run dev
```

- App: http://localhost:5173
- Unit and component tests: `npm test`
- Production build: `npm run build` (output in `frontend/dist/`)
- End-to-end tests: `npm run test:e2e` (builds, then drives the installed Microsoft Edge with Playwright; set `PW_CHANNEL=chrome` to use Chrome)

| Variable | Default | Purpose |
| --- | --- | --- |
| `VITE_API_BASE_URL` | `http://127.0.0.1:8000` | Backend address. Set it in `frontend/.env.local` for development, or in the host's build settings for deployment |

`VITE_*` values are compiled into the public browser bundle, so this file must only ever hold the backend URL, never a secret. `frontend/.env.local` is ignored by Git.

Run the backend and the frontend in two separate terminals. The frontend footer shows whether it can reach the backend.

### Using it

1. Open the **Workspace**, choose a WAV, MP3, OGG or FLAC file, and optionally paste the text you were delivering and add a reference recording of the same text. Once a reference is chosen you can also give its own text separately; if the two texts contain different words, the recordings are not compared word for word.
2. Press **Run analysis**. The file goes to `POST /api/analyze` on your backend.
3. The result shows which steps completed, the recognised text, a time for each word and how many findings there are. **Open the dashboard** for the findings with their intervals and evidence, the rules that were checked or withheld, the waveform, playback (select a word or a finding to play from it), measured contours, and each metric's method and limitations.
4. The **Acoustic Twin** shows the same recording's measured energy and pitch in 3D (or 2D).
5. **Evidence Coach** shows the rule-based suggestions for your findings, and **Reports** a printable summary of the status, findings, suggestions and what could not be checked.

The dashboard lists each recording's transcript and where it came from separately, and warns when less than 80% of the transcript could be compared. Findings and suggestions for your recording come only from the rules described under [Findings](#findings-apianalyze). Ticking "I have checked this transcript against the recording" is recorded as your statement; the app never describes a transcript as verified.

## API

All routes are under `/api`. Upload routes take a multipart form with `file` (WAV, FLAC, OGG or MP3). Uploads are processed in memory and not stored. All times are in seconds.

| Route | Form fields | Returns |
| --- | --- | --- |
| `GET /api/health` | — | Status, version, upload limits, and transcription engine status |
| `POST /api/features` | `file`, optional `transcript` | Acoustic measurements |
| `POST /api/transcribe` | `file`, optional `language` | Text, segments and word timestamps |
| `POST /api/align` | `file`, optional `transcript`, optional `language` | Start and end time for each transcript word |
| `POST /api/analyze` | `file`, optional `reference`, `transcript`, `reference_transcript`, `transcript_reviewed`, `reference_transcript_reviewed`, `language` | The main route: measurements, transcription, alignment, signal quality, findings and rule-based suggestions |
| `POST /api/analyses` | JSON body: an `/api/analyze` result | Optional saving: an ID and a one-time access key |
| `GET`, `DELETE /api/analyses/{id}` | header `X-Access-Key` | Open or delete a saved analysis |
| `POST /api/compare` | `reference`, `participant`, optional `transcript`, optional `language` | Measured differences between two recordings of the same text |

```powershell
curl.exe -F "file=@talk.wav" -F "transcript=Good morning everyone" http://127.0.0.1:8000/api/analyze
```

Errors always have the shape `{"detail": {"code": "...", "message": "..."}}` and never contain file paths, credentials or stack traces. Common codes: `empty_upload`, `unsupported_audio`, `undecodable_audio`, `audio_too_short`, `audio_too_long`, `sample_rate_too_low`, `too_many_channels`, `upload_too_large`, `invalid_request`, `processing_failed`, `missing_dependency`, `model_download_failed`, `model_load_failed`, `hf_auth_required`, `hf_auth_rejected`, `transcription_failed`, `empty_transcript`, `no_word_timestamps`.

### Acoustic features (`/api/features`)

Every metric carries a `status`, the `method` used and its `limitations`.

| Metric | Status | How |
| --- | --- | --- |
| Duration, sample rate, channels, peak amplitude | measured | Decoded with libsndfile; analysed as mono at 16 kHz |
| Waveform peaks | measured | Largest amplitude in each of 1000 time buckets |
| Clipping | measured, with a verdict | Flat-topped peaks counted on the decoded samples before mixing or resampling. `detected` needs 3 or more; a few, a full-scale peak without flat tops, or a loud lossy file give `uncertain` |
| Frame energy | measured | RMS in dBFS, 25 ms frames every 10 ms |
| Spectral centroid, bandwidth, roll-off, flatness, zero-crossing rate | measured | STFT (librosa) |
| MFCCs | measured | 13 coefficients; mean and standard deviation returned |
| F0 / pitch contour | measured, with `reliability` | Praat via Parselmouth (pYIN fallback), in two passes: 50–600 Hz, then a range fitted to the speaker. `reliability` is `low` when octave jumps or too little voicing are seen |
| Pause intervals | measured, with `reliability` | Quiet recordings: silence 25 dB below the speech level. Noisy recordings: silence within 3 dB of the noise floor. At least 0.25 s. `unavailable` when speech cannot be separated from the background |
| Speaking rate (syllables per second) | **estimated** | Energy-peak syllable nuclei; not validated against hand counts |
| Words per minute | **estimated** | Transcript word count over duration |

Frame series longer than 3000 points are thinned and report their actual hop.

### Transcription (`/api/transcribe`)

Returns the recognised text, segments, and for each word its start, end and the model's own probability. `status` is `no_speech` when nothing was recognised, and `word_timestamps` is `unavailable` if the model returned text without word times. The text is a model's best guess and can contain errors.

### Alignment (`/api/align`)

Gives each word of your transcript a status:

- `aligned`: the word was recognised at that position; the times are for that word.
- `substituted`: a different word was recognised in its place (`recognized_as`); the times are for the recognised word.
- `unaligned`: nothing could be matched; `start` and `end` are null rather than guessed.

Words the recogniser heard that are not in the transcript are listed in `unmatched_recognized`. If no transcript is sent, the recognised text is aligned to itself (`transcript_source: "transcribed"`).

**Method and limits.** The recording is transcribed with word timestamps, then transcript words are matched in order to recognised words. This is not phoneme-level acoustic forced alignment: a word the recogniser misses gets no time, different spellings such as "3" and "three" do not match, and timing is accurate to roughly a tenth of a second.

### Raw comparison (`/api/compare`)

The measured differences on their own, without rules. `/api/analyze` with a `reference` returns these too. Upload a `reference` and a `participant` recording of the same text. Both are aligned to the supplied transcript, or to the text recognised in the reference if none is sent. The response contains:

- **Global differences:** duration, pause count and total, pitch range and interquartile range in semitones, and speaking-rate estimates. Each says whether it is `measured` or `estimated` and whether the two values are fairly `comparable`. Median pitch in Hz is shown but marked not comparable, and loudness is left out, because both depend on the speaker or the microphone rather than the delivery.
- **Timing differences:** gaps between consecutive words that are at least 0.25 s longer or shorter than in the reference, with the interval in each recording and the evidence. Only gaps between words recognised at the same position in both recordings are measured.

These are **differences, not flaws**. Nothing is labelled a flaw, given a severity or turned into coaching; `not_implemented` in the response lists what is missing.

**Measured accuracy.** `python -m app.comparison.evaluate` checks the comparison against the demonstration dataset, where pauses were inserted at known times. With the `base` transcription model on the development machine: 14 of 21 inserted pauses were reported as a longer gap, 0 longer gaps matched no inserted pause, 3 shorter gaps were reported although none was made shorter, and 6 timing differences were reported across 24 control samples whose timing is identical to the reference. Pauses are missed mainly because the recogniser stretches a word across the silence instead of leaving a gap. This is 3 speakers and transformed audio, so it indicates behaviour, not real-world accuracy.

### Findings (`/api/analyze`)

Send the participant recording as `file`. Optionally add a `reference` recording of the same text, a `transcript`, and a `reference_transcript`. Invalid uploads return an error; everything else returns 200 with a `status`:

| `status` | Meaning |
| --- | --- |
| `completed` | Rules ran and at least one finding crossed its threshold |
| `completed_no_findings` | Rules ran and nothing crossed a threshold |
| `partial` | Something could not run (unusable audio, no transcription, a reference that could not be used). `rules` and `limitations` say what and why |

**How recordings are compared.** Both are aligned to one shared transcript: a supplied one, or the text recognised in the reference. A word is compared only if it was recognised at that position in both recordings, so every measurement covers the same spoken words; raw timestamps are never compared across recordings. The comparison is withheld, with the reason in `alignment_status`, when the two transcripts differ, when fewer than 60% of the words are recognised in either recording, or when fewer than 10 words line up. Words are also left out when a match stands alone with no matched neighbour, which is where a repeated word gets matched to the wrong place; `alignment_status.words_excluded` counts every omission by reason, and `unmatched_recognised` counts words heard in each recording that are not in the transcript at all; those are never compared or treated as delivery differences. When less than 80% of the transcript could be compared, reference-based findings are rated at most `moderate` and say so.

**Transcript provenance.** `transcripts` gives, separately, each recording's own text and the text both were aligned to. Each has a `source` (`user_provided` or `machine_generated`) and a `review_status`. Sending `transcript_reviewed=true` with a transcript you supplied records `user_attested`: your statement that you checked it, which the API cannot verify. `human_verified` is always false, and machine-generated text can never be marked reviewed. A text checked against one recording has not been checked against the other, so the shared text is marked `user_attested` only when you vouched for it on both recordings; `attested_for` lists which. If a response carries no provenance at all, the app shows "Provenance unknown".

**Rules.** Each has an ID, its thresholds in the response, and one of four outcomes in `rules`: `triggered`, `not_triggered`, `withheld` (with the reason) or `not_supported`.

| Category | With a reference | Without a reference | Severity |
| --- | --- | --- | --- |
| Rushed / slow delivery | Speaking time for the same words, pauses removed, differs by more than 10% | Recognised words per minute above 200 or below 100 (English only, at least 20 words over 8 s) | With a reference only: minor, moderate from 20%, major from 35% |
| Excessive pause | A measured pause at least 0.4 s longer than the reference's silence at the same words | A measured pause of 1.5 s or more | With a reference only: minor, moderate from 0.8 s, major from 1.5 s extra |
| Pause placement | A place where the reference pauses and the participant's silence at the same words is at least 0.4 s shorter; reference pauses falling between the same two aligned words are compared once, together | Withheld: where pauses belong depends on the text | None |
| Uneven pacing | Pace per run of about 5 words, relative to the speaker's overall pace, varies by 1.5x or more; stretches off by 25% are reported | Withheld | None |
| Filler words | Recognised hesitation sounds (um, uh, er, erm, hmm, mm, including drawn-out spellings) at their word times. Below 0.5 recogniser probability they are reported as "possible" with low evidence quality. The count is a lower bound: this is transcript-based, not audio-level detection, and recognisers often omit fillers | Same | None |
| Pitch variation ("possibly narrow") | Pitch range over voiced frames, in semitones around each speaker's own median, at most 70% of the reference's | Range below 4 semitones | None |
| Articulation / clarity | Not supported | Not supported | — |

Every finding carries a stable `id`, the interval in the participant audio, the measured `evidence` with units and reference values, the `comparison_method`, the `rule` and thresholds, an `evidence_quality`, an `explanation` and its `limitations`.

**Severity** is a band of the measured size of a difference, given only by the two reference-based rules above. It is not a rating of how the delivery sounds. All thresholds are in `DetectionSettings` (`backend/app/detection/schemas.py`) and echoed in the response as `settings`.

**Safeguards.**

- Silent, steady-noise or very short recordings are reported as not usable and no rule runs.
- Detected clipping, low-confidence pause detection in noise, and unreliable pitch tracking lower `evidence_quality` to `low`, remove severity, and word the finding as "possible".
- Pitch rules are withheld, not guessed, when pitch tracking is unreliable. Tracking is checked directly: if the result changes when the tracker's lower limit is nudged, which happens with creaky or very low voices, the recording is flagged. Low voices that track stably are measured normally.
- Pitch is only ever compared in semitones relative to the speaker, so a naturally high or low voice changes nothing. Loudness, spectral and MFCC features are not compared, because they depend on the microphone and the voice.
- Findings are measured differences, not proof of a problem, a diagnosis, or a statement about cause.

**Measured behaviour on the demonstration dataset.** `python -m app.detection.evaluate` analyses every dataset sample against its own reference with the real `base` transcription model. On the development machine:

| Labelled flaw in the dataset | Mild | Moderate | Severe | Near-reference |
| --- | --- | --- | --- | --- |
| Excessive pauses | 3 of 3 | 3 of 3 | 3 of 3 | 0 of 3 (inserted pause is below the threshold) |
| Rushed delivery | 3 of 3 | 3 of 3 | 3 of 3 | 0 of 3 |
| Slow delivery | 3 of 3 | 3 of 3 | 3 of 3 | 0 of 3 |
| Uneven pacing | 0 of 3 | 3 of 3 | 3 of 3 | 0 of 3 |
| Pitch monotony | 2 of 3 | 1 of 3 | 2 of 3 | 0 of 3 |
| Unclear articulation (no rule) | 0 of 3 | 0 of 3 | 0 of 3 | 0 of 3 |

In total the labelled flaw was reported for 38 of 45 mild-to-severe samples, and nothing was reported for the 3 references or the 12 unclear-articulation samples. Severity bands followed the dataset's tiers for pace (minor, moderate, major) and pauses. Five findings were of a category other than the label: four "slow delivery" on uneven-pacing samples, whose transform does make them longer overall, and one pause on a slowed sample. Pitch findings were withheld for 26 samples because tracking was flagged unreliable, almost all from the low-voiced speaker.

Two further checks were run once on the development machine:

- **Pause placement.** With the roles swapped, so that each pause-inserted sample is the reference and the original is the participant, 16 of the 21 inserted pauses were reported as a shorter or missing pause, none was reported elsewhere, and none was reported across 27 samples with identical timing. Three of the five misses are 0.35 s pauses, below the 0.4 s threshold.
- **Fillers.** The dataset has no fillers, so three short clips were synthesised locally with the Windows text-to-speech voice (not committed, because the voice's redistribution terms are unclear). The model returned all 9 fillers in the two clips that had them, one as a different filler ("hmm" heard as "um"), and none in the clip without. Synthesised fillers are clearly pronounced; real hesitations are quieter and more likely to be dropped, so this is a best case.

Read these numbers with care. The uneven-pacing and pitch thresholds were chosen using this same dataset, so their results here are optimistic. The dataset is 3 speakers of transformed audio, so this shows how the rules behave, not how accurate they are on natural speech.

**Suggestions.** `coaching` holds one tip per kind of finding: fixed wording chosen by the rule that produced the findings. Each tip carries `evidence` (for every finding behind it: the interval, the measured feature and unit, your value, the reference value or null, and the difference), a `reason` that explains how that measurement leads to the suggestion, and a `certainty` of `confirmed` or `uncertain` (uncertain when any finding's evidence is weak, or the rule only claims a possibility, as the pitch rules do). The Evidence Coach page also lists what could not be assessed. There is no language model: the deterministic rules are the only path, so nothing needs a key, and no tip exists without a finding or says why a difference occurred.

Acoustic features are always returned for valid audio. If transcription or alignment cannot run, that part is `null`, `components` gives its `status`, `code` and `message`, and rules that need words are withheld, so a missing model never blocks the acoustic measurements.

## Dataset

`data/` holds a small contrastive speech dataset: three public-domain LibriVox recordings (three speakers) and, for each, 28 deliberately flawed versions made by signal processing (the filler versions use synthetic filler sounds), with the altered intervals recorded exactly. Read [`data/DATASET_CARD.md`](data/DATASET_CARD.md) before using it; in short, the flawed samples are transforms of real recordings, not natural flawed speech, and nothing has been manually annotated.

From `backend/`:

```powershell
python -m app.dataset build                                   # regenerate all 87 samples (about 22 MB, not in Git)
python -m app.dataset validate ..\data\speakiq-contrastive-v1  # check manifest and audio files
python -m app.dataset validate ..\data\examples                # check the 7 committed example files
python -m app.dataset check                                   # validate committed files and confirm a rebuild matches
python -m app.dataset transcripts status                      # which transcripts a person has verified (none yet)
python -m app.dataset transcripts review --reviewer "Name"    # play each clip and confirm or fix its transcript
python -m app.dataset export                                  # package for upload; uploads nothing
```

The build needs no network access and is deterministic. Transcripts are unverified machine output until someone records a review; the dataset is not published. See the dataset card for the verification workflow and [`data/HOSTING.md`](data/HOSTING.md) for publishing. `pytest tests/test_dataset.py tests/test_stress.py` runs the dataset validation tests and the audio stress tests.

## Saving analyses (optional)

Analyses normally live only in the browser tab and are lost on reload. Saving them needs a Supabase project, and stays switched off until you configure it; everything else works without it.

**What is stored:** the analysis result, including transcript text. **Audio is never stored.** There are no user accounts, so access works by possession of a secret: saving returns an ID and an access key, only a hash of the key is stored, and opening or deleting needs both. There is no way to list saved analyses, and a wrong ID or key gets the same "not found" answer.

To switch it on:

1. In your Supabase project's SQL editor, run [`docs/supabase/schema.sql`](docs/supabase/schema.sql). It creates the `analyses` table with row-level security on and no policies, so the public anon key cannot read or write it.
2. In `backend/.env`, set `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` (Project Settings > API). The service-role key has full database access: keep it in the backend only, never in a `VITE_` variable.
3. Restart the backend. `/api/health` then reports `"persistence": {"configured": true}`.

Then use **Save this analysis** on the dashboard, and **Open a saved analysis** in the workspace. A saved analysis opens without playback, because its audio was not kept.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| Frontend footer says "Backend not reachable" | Start the backend, and check that `VITE_API_BASE_URL` in `frontend/.env.local` matches its address. Restart `npm run dev` after editing env files |
| Browser console shows a CORS error | Add the frontend's origin to `BACKEND_CORS_ORIGINS` and restart the backend |
| First transcription request is very slow | The model is downloading. Run `python -m app.speech.prefetch` once |
| `model_download_failed` | No internet connection while the model is not yet cached. Go online and run the prefetch command |
| `hf_auth_required` | `WHISPER_MODEL` points at a private or gated repository. Set `HF_TOKEN` in `backend/.env`, or switch back to a public model such as `base` |
| `hf_auth_rejected` | The configured `HF_TOKEN` is invalid or lacks access to the model |
| `missing_dependency` | Run `pip install -r requirements.txt` inside the backend virtual environment |
| `model_load_failed` | Check `WHISPER_MODEL`, `WHISPER_DEVICE` and `WHISPER_COMPUTE_TYPE`. `cuda` needs an NVIDIA GPU with CUDA libraries |
| Windows: the backend process exits abruptly on the first transcription | An old system Microsoft C++ runtime. `requirements.txt` installs the `msvc-runtime` package to work around this; make sure it is installed in the virtual environment, or install the latest "Microsoft Visual C++ Redistributable (x64)" |
| `persistence_not_configured` when saving | Saving is off. Set `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` in `backend/.env` and restart, or ignore it: saving is optional |
| `persistence_failed` or `persistence_unavailable` | Supabase refused or could not be reached. Check the URL, the service-role key, and that `docs/supabase/schema.sql` was run |
| `unsupported_audio` for M4A or WebM | The backend decodes WAV, FLAC, OGG and MP3 only. Convert the file first |
