# SpeakIQ AI Coach

**Evidence-first speech delivery analysis with temporally grounded explanations.**

SpeakIQ AI Coach finds delivery flaws in a speech recording (long pauses, rushed or slow pace, uneven pacing, filler sounds, flat pitch), pins each one to an exact time interval, and shows the measurement that proves it.

Built for the **Multimodal AI Hackathon 2026** (KamandPrompt, IIT Mandi) · **Track C: Contrastive Speech Analytics & Temporal Flaw Grounding**

---

## Links

| | Link |
| --- | --- |
| 🌐 Live demo (frontend, Vercel) | https://speakiq-ai-coach.vercel.app |
| ⚙️ Backend API (Render) | https://speakiq-ai-coach-api.onrender.com |
| 📄 API documentation (Swagger) | https://speakiq-ai-coach-api.onrender.com/docs |
| ❤️ Backend health check | https://speakiq-ai-coach-api.onrender.com/api/health |
| 💻 Source code (GitHub) | https://github.com/mokshadpoojary9-bot/speakiq-ai-coach |
| 🎥 Demo video (YouTube) | _add your YouTube link here_ |

> The backend runs on Render's free plan. After a period of inactivity it sleeps, so the **first analysis can take 1–2 minutes** while it wakes up and loads the speech model. Later runs are much faster. The hosted backend accepts recordings up to **60 seconds**.

---

## The problem

Competitive speaking (declamation, debate, oratory, interpretive reading) is judged largely by ear. Judges weigh tone, pace, volume and pauses differently, so scores are inconsistent, and speakers receive vague feedback such as "work on your pacing" without learning **where** in the speech it went wrong or **by how much**. There is also no public dataset that pairs a good delivery with a graded range of flawed deliveries of the **same text**.

## The solution

SpeakIQ compares a speaker's recording with a **reference recording of the same words**, aligns them word by word, and reports each deviation as a finding with:

- the **exact interval** in seconds,
- the **measured evidence** (your value, the reference value and the difference, with units),
- the **rule and threshold** that was crossed,
- an **explanation** and the measurement's **limitations**.

When the system cannot measure something reliably, it **withholds** the result and says why, instead of guessing.

---

## Features

### Analysis
- **Acoustic feature extraction:** frame energy (RMS, dBFS), spectral centroid, bandwidth, roll-off, flatness and zero-crossing rate (STFT), 13 MFCCs, F0/pitch contour (Praat via Parselmouth), pause intervals, speaking rate.
- **Local transcription** with faster-whisper, with a start and end time for every word. No paid API keys are needed.
- **Word alignment** of a transcript to the recording; reference and participant are compared **only on the same words**.
- **Rule-based findings** for rushed or slow delivery, excessive pauses, pause placement, uneven pacing, filler words (including an acoustic check for fillers the recogniser misses) and narrow pitch variation.
- **Severity bands** (minor, moderate, major) for pace and pause differences against a reference.
- **Recording-quality checks:** clipping, noisy-pause confidence and pitch-tracking reliability. Weak evidence lowers confidence and the finding is worded as "possible".
- **Speaker-agnostic comparison:** pitch is compared in semitones relative to each speaker's own median; loudness, spectral and MFCC values are never compared across speakers.

### Interactive dashboard
- **Workspace:** upload a recording (WAV, MP3, OGG, FLAC), an optional reference recording and an optional transcript; validation, waveform and playback.
- **Dashboard:** findings with intervals and evidence, rules checked or withheld, waveform, measured contours, and click-to-play on any word or finding.
- **Acoustic Twin:** a 3D view of the recording's energy (bars) and pitch (line), with silences highlighted and an accessible 2D table fallback.
- **Evidence Coach:** one rule-based suggestion per kind of finding, each showing the measurement it comes from. No language model is used, and no tip exists without a finding.
- **Reports:** a printable summary of status, findings, suggestions and what could not be checked (Print or save as PDF).
- **Optional saving** to Supabase: analysis results only, **never audio**, opened with an ID and a one-time access key.
- Demo data is always clearly labelled; real analyses carry a "Real analysis" label.

---

## Contrastive dataset

No public dataset maps good delivery against flawed delivery of the same text, so one was built for this project: **`speakiq-contrastive-v1`**.

| | |
| --- | --- |
| Source recordings | 3 public-domain LibriVox recordings (LibriSpeech), 3 different speakers |
| Samples | **87** = 3 references + 84 flawed variants |
| Flaw categories | 7: excessive pauses, rushed, slow, uneven pacing, pitch monotony, unclear articulation (proxy), filler words (synthetic, proxy) |
| Severity tiers | 4 per category: near-reference, mild, moderate, severe |
| Labels | Flaw intervals known exactly by construction |
| Audio | FLAC, 16-bit, mono, 16 kHz, about 23 minutes in total |
| Reproducibility | Deterministic build (fixed seed), checksummed sources, schema-validated manifest |

Details: [`data/DATASET_CARD.md`](data/DATASET_CARD.md). Eight example files are committed in [`data/examples/`](data/examples/); the full set is rebuilt with `python -m app.dataset build`.

> The flawed samples are signal-processing transforms of real recordings, not natural flawed performances. Filler and articulation labels are proxies.

---

## Results on the dataset

Measured with `python -m app.detection.evaluate` (each sample analysed against its own reference):

| Labelled flaw | Mild | Moderate | Severe | Near-reference |
| --- | --- | --- | --- | --- |
| Excessive pauses | 3 / 3 | 3 / 3 | 3 / 3 | 0 / 3 |
| Rushed delivery | 3 / 3 | 3 / 3 | 3 / 3 | 0 / 3 |
| Slow delivery | 3 / 3 | 3 / 3 | 3 / 3 | 0 / 3 |
| Uneven pacing | 0 / 3 | 3 / 3 | 3 / 3 | 0 / 3 |
| Pitch monotony | 2 / 3 | 1 / 3 | 2 / 3 | 0 / 3 |

- The labelled flaw was reported in **45 of 54** mild-to-severe samples.
- **No findings** on the 3 clean references or the 12 unclear-articulation samples.
- Filler detection: **1 / 24** with the recogniser alone, **16 / 24** with the acoustic filled-pause check.

> These results come from 3 speakers and transformed audio, and some thresholds were chosen on this same data. They show how the rules behave, not real-world accuracy.

---

## Architecture

```
Browser (React + Vite, hosted on Vercel)
        │  POST /api/analyze  (audio + optional reference + optional transcript)
        ▼
FastAPI backend (hosted on Render)
  ├── app/audio/        acoustic feature extraction (librosa, Praat-Parselmouth)
  ├── app/speech/       transcription and word alignment (faster-whisper)
  ├── app/comparison/   reference-vs-participant differences
  ├── app/detection/    signal quality, rule-based findings, coaching
  ├── app/persistence.py optional Supabase storage (results only)
  └── app/dataset/      dataset build, validation and export
```

## Tech stack

| Layer | Tools |
| --- | --- |
| Frontend | React, Vite, TypeScript, Tailwind CSS, Recharts, wavesurfer.js, React Three Fiber (three.js) |
| Backend | Python, FastAPI, NumPy, SciPy, librosa, Praat-Parselmouth, faster-whisper |
| Storage (optional) | Supabase (row-level security, hashed access keys) |
| Hosting | Vercel (frontend), Render (backend) |
| Testing | pytest, Vitest, Playwright |
| Development | Built with Claude Code as a coding assistant |

---

## API

All routes are under `/api`. Interactive docs: https://speakiq-ai-coach-api.onrender.com/docs

| Route | Purpose |
| --- | --- |
| `GET /api/health` | Status, version, limits and transcription engine status |
| `POST /api/analyze` | **Main route:** measurements, transcription, alignment, quality checks, findings and suggestions |
| `POST /api/features` | Acoustic measurements only |
| `POST /api/transcribe` | Text and word timestamps |
| `POST /api/align` | Start and end time for each transcript word |
| `POST /api/compare` | Raw measured differences between two recordings |
| `POST /api/analyses`, `GET`/`DELETE /api/analyses/{id}` | Optional saving and opening of results |

---

## Run locally

**Prerequisites:** Python 3.11+, Node.js 20+, about 150 MB for the speech model.

**Backend** (from `backend/`):

```bash
python -m venv .venv
# Windows: .\.venv\Scripts\Activate.ps1   |   macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
python -m app.speech.prefetch          # download the speech model once
uvicorn app.main:app --reload --port 8000
```

**Frontend** (from `frontend/`):

```bash
npm install
cp .env.example .env.local             # Windows: Copy-Item .env.example .env.local
npm run dev                            # http://localhost:5173
```

**Tests:** `pytest` (backend) and `npm test` (frontend).

**Dataset:**

```bash
python -m app.dataset build                                    # rebuild all 87 samples
python -m app.dataset validate ../data/speakiq-contrastive-v1  # check manifest and audio
python -m app.detection.evaluate                               # reproduce the results table
```

### Environment variables

| Where | Variable | Purpose |
| --- | --- | --- |
| Backend | `BACKEND_CORS_ORIGINS` | Frontend address allowed to call the API |
| Backend | `WHISPER_MODEL` | Speech model (`tiny` on Render, `base` by default) |
| Backend | `MAX_AUDIO_SECONDS` | Longest accepted recording (60 on Render) |
| Backend (optional) | `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | Enable saving results. Keep the key on the backend only |
| Frontend | `VITE_API_BASE_URL` | Backend address. Public, never a secret |

Deployment steps: [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) · Render config: [`render.yaml`](render.yaml) · Vercel config: [`frontend/vercel.json`](frontend/vercel.json)

---

## Limitations

- Word alignment uses recogniser word timestamps, not phoneme-level forced alignment; timing is accurate to roughly a tenth of a second.
- The recogniser can stretch a word over a short silence, so some pauses are missed.
- Filler counts are a lower bound; natural fillers are untested.
- No clarity or articulation finding is produced, because those measures penalise accent, voice and microphone.
- The dataset is small (3 speakers) and its flaws are synthetic transforms.

## What's next

- Test on natural flawed speech from more speakers
- Phoneme-level forced alignment for tighter timestamps
- Publish the dataset publicly

---

## Author

**Moksha D Poojary**, solo participant
📧 mokshadpoojary9@gmail.com · mokshadpoojary284@gmail.com
💻 https://github.com/mokshadpoojary9-bot

## License and attribution

Source audio: LibriVox (public domain), distributed by LibriSpeech (CC BY 4.0, Panayotov et al., 2015), obtained via librosa's example files. Derived dataset offered under CC BY 4.0 with the same attribution. See [`data/DATASET_CARD.md`](data/DATASET_CARD.md).

