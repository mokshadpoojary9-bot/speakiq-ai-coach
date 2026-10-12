# SpeakIQ AI Coach

Evidence-first speech delivery analysis with temporally grounded explanations, built for the track **Contrastive Speech Analytics & Temporal Flaw Grounding**.

The full specification lives in [`docs/PROJECT_SPEC.yaml`](docs/PROJECT_SPEC.yaml) and is the source of truth for every milestone.

## Status

| Area | State |
| --- | --- |
| Backend API: health, acoustic features, transcription, word alignment, combined analysis | Working (see [API](#api)) |
| Local transcription with faster-whisper | Working; no Hugging Face token needed for the default model |
| Frontend pages: landing, workspace, dashboard, Acoustic Twin, Evidence Coach, reports | Working |
| Audio file validation, playback and waveform in the workspace | Working, in the browser only |
| Workspace → backend: upload a recording, get real measurements, transcript and word timing | Working (`POST /api/analyze`) |
| Dashboard and Acoustic Twin for your recording | Working with real backend results; switchable to the demo fixture |
| Findings, baseline comparison charts, coaching text and report content | **Demo fixture** (`frontend/src/fixtures/demoAnalysis.ts`), not computed from audio. Evidence Coach and Reports are demo-only |
| Contrastive demonstration dataset: 3 real recordings, 72 transformed variants, schema, validator, dataset card | Built and validated (see [Dataset](#dataset)) |
| Baseline comparison and flaw detection | Not implemented yet |
| Free-form coach questions, language model, Supabase, hosting | Not implemented or connected |

Every frontend view that shows fixture data carries a "Demo data — not a real analysis" label, and views of your own recording carry a "Real analysis" label. A real analysis is kept in browser memory only and is lost when the page is reloaded. No paid API keys are needed to run the project locally.

## Repository layout

```
frontend/   React + Vite + TypeScript + Tailwind CSS
backend/    Python + FastAPI
  app/audio/    acoustic feature extraction
  app/speech/   transcription and word alignment
  app/dataset/  dataset schema, transforms, build and validation
data/       contrastive dataset: sources, examples, manifest, schema, dataset card
docs/       Project specification
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
| `WHISPER_MODEL` | `base` | faster-whisper model name or Hugging Face repository |
| `WHISPER_DEVICE` | `cpu` | `cpu` or `cuda` |
| `WHISPER_COMPUTE_TYPE` | `int8` | For example `int8`, `float32` |
| `WHISPER_LANGUAGE` | empty (auto-detect) | Force a language code such as `en` |
| `WHISPER_DOWNLOAD_ROOT` | empty (Hugging Face cache) | Where to store the model |
| `HF_TOKEN` | empty | **Secret.** Only needed if `WHISPER_MODEL` points at a private or gated repository |

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

1. Open the **Workspace**, choose a WAV, MP3, OGG or FLAC file, and optionally paste the text you were delivering.
2. Press **Run analysis**. The file goes to `POST /api/analyze` on your backend.
3. The result shows which steps completed, the recognised text and a time for each word. **Open the dashboard** for the waveform, playback (select a word to play from it), measured pitch, energy and spectral contours, detected pauses, and each metric's method and limitations.
4. The **Acoustic Twin** shows the same recording's measured energy and pitch in 3D (or 2D).

Real recordings have no findings, severities or coaching yet, because flaw detection and baseline comparison are not implemented. The app says so rather than showing demo findings as yours.

## API

All routes are under `/api`. Upload routes take a multipart form with `file` (WAV, FLAC, OGG or MP3). Uploads are processed in memory and not stored. All times are in seconds.

| Route | Form fields | Returns |
| --- | --- | --- |
| `GET /api/health` | — | Status, version, upload limits, and transcription engine status |
| `POST /api/features` | `file`, optional `transcript` | Acoustic measurements |
| `POST /api/transcribe` | `file`, optional `language` | Text, segments and word timestamps |
| `POST /api/align` | `file`, optional `transcript`, optional `language` | Start and end time for each transcript word |
| `POST /api/analyze` | `file`, optional `transcript`, optional `language` | Features, transcription and alignment together |

```powershell
curl.exe -F "file=@talk.wav" -F "transcript=Good morning everyone" http://127.0.0.1:8000/api/analyze
```

Errors always have the shape `{"detail": {"code": "...", "message": "..."}}`. Common codes: `empty_upload`, `unsupported_audio`, `undecodable_audio`, `audio_too_short`, `audio_too_long`, `upload_too_large`, `invalid_request`, `missing_dependency`, `model_download_failed`, `model_load_failed`, `hf_auth_required`, `hf_auth_rejected`, `transcription_failed`, `empty_transcript`, `no_word_timestamps`.

### Acoustic features (`/api/features`)

Every metric carries a `status`, the `method` used and its `limitations`.

| Metric | Status | How |
| --- | --- | --- |
| Duration, sample rate, channels, peak amplitude | measured | Decoded with libsndfile; analysed as mono at 16 kHz |
| Waveform peaks | measured | Largest amplitude in each of 1000 time buckets |
| Frame energy | measured | RMS in dBFS, 25 ms frames every 10 ms |
| Spectral centroid, bandwidth, roll-off, flatness, zero-crossing rate | measured | STFT (librosa) |
| MFCCs | measured | 13 coefficients; mean and standard deviation returned |
| F0 / pitch contour | measured | Praat via Parselmouth, falling back to librosa pYIN; `unavailable` if neither runs |
| Pause intervals | measured | Silence more than 25 dB below the loudest frame for at least 0.25 s |
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

### Combined analysis (`/api/analyze`)

Runs all three. Acoustic features are always returned for valid audio. If transcription or alignment cannot run, that part is `null` and `components` gives its `status`, `code` and `message`, so a missing model never blocks the acoustic measurements.

## Dataset

`data/` holds a small contrastive speech dataset: three public-domain LibriVox recordings (three speakers) and, for each, 24 deliberately flawed versions made by signal processing, with the altered intervals recorded exactly. Read [`data/DATASET_CARD.md`](data/DATASET_CARD.md) before using it; in short, the flawed samples are transforms of real recordings, not natural flawed speech, and nothing has been manually annotated.

From `backend/`:

```powershell
python -m app.dataset build                                   # regenerate all 75 samples (about 19 MB, not in Git)
python -m app.dataset validate ..\data\speakiq-contrastive-v1  # check manifest and audio files
python -m app.dataset validate ..\data\examples                # check the 7 committed example files
```

The build needs no network access and is deterministic. `pytest tests/test_dataset.py tests/test_stress.py` runs the dataset validation tests and the audio stress tests.

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
| `unsupported_audio` for M4A or WebM | The backend decodes WAV, FLAC, OGG and MP3 only. Convert the file first |
