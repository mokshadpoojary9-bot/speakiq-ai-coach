# SpeakIQ AI Coach — final technical audit

Date: 2026-10-14. Track: Contrastive Speech Analytics & Temporal Flaw Grounding.

This audit checks the repository against `docs/PROJECT_SPEC.yaml`. Every result below comes from a command run for this audit on the development machine (Windows 11, Python 3.14 and 3.13, Node 24). "Works" means the software does what it is designed to do and its tests pass; it does not mean the detection thresholds are valid on natural speech, which has not been tested with listeners.

## 1. Verification results

| Check | Command | Result |
| --- | --- | --- |
| Backend tests, Python 3.14 | `pytest` in `backend/` | 460 passed |
| Backend tests, Python 3.13 (fresh environment from `requirements-dev.txt`) | same | 460 passed |
| Frontend unit and component tests | `npm test` | 106 passed |
| Frontend production build | `npm run build` | succeeded |
| Browser end-to-end tests (Microsoft Edge) | `npm run test:e2e` | 7 passed |
| Full dataset, manifest and audio | `python -m app.dataset validate ../data/speakiq-contrastive-v1` | 0 errors, 0 warnings |
| Committed example set | `python -m app.dataset validate ../data/examples` | 0 errors, 0 warnings |
| Dataset rebuild reproduces committed manifests | `python -m app.dataset check` | passed after the dataset 1.1.0 rebuild |
| Detection rules on the dataset (real `base` model) | `python -m app.detection.evaluate` | labelled flaw reported for 45 of 54 mild-to-severe samples (38 of the 45 non-filler ones, unchanged); 12 findings of another category; 16 of 24 inserted synthetic fillers found (1 before the acoustic check) |
| Pitch tracking reliability | `python -m app.audio.evaluate_pitch` | 24 of 87 recordings withheld, 0 false readings among those reported |
| Peak memory of one analysis (`tiny`, 60 s recording and reference) | measured on the development machine | 471 MB (Windows working set) |
| Transcript review status | `python -m app.dataset transcripts status` | all 3 sources `unverified` |

Not run anywhere: deployment to Render or Vercel, a real Supabase project, Linux or macOS, and any test with listeners or natural flawed speech.

## 2. Specification coverage

### Dataset

| Requirement | Status | Where |
| --- | --- | --- |
| Paired baseline and flawed examples with the same transcript | Done | `data/`, 3 pairs of 25 samples |
| Multiple flaw types and a severity gradient | Done, with limits | 7 of 7 categories, 4 tiers each. Tiers are transform strengths, not perceptual ratings. Filler samples use synthetic filler sounds |
| Transcripts, metadata, labels and intervals stored with the audio | Done | `data/speakiq-contrastive-v1/manifest.json` |
| Small, well-labelled, reproducible | Done | Byte-identical rebuilds on this machine; seeded |
| Provenance, generation, licensing and limitations documented | Done | `data/DATASET_CARD.md`. Licensing is the project's reading of upstream terms |

### Audio analysis

| Requirement | Status | Where |
| --- | --- | --- |
| Waveform and spectral features | Done | `backend/app/audio/features.py` |
| MFCCs, F0 contour, speech rate, pauses, energy, clarity proxies | Done, clarity as an estimate | Articulation rate and recogniser word confidence are reported and shown labelled as an estimate (`backend/app/detection/clarity.py`); they never produce a finding, because accent, voice and microphone affect them too |
| Forced alignment of transcript words | Partial | Transcript-to-recognition alignment using Whisper word timestamps, not phoneme-level acoustic forced alignment. Documented in the README |
| Careful speaker normalisation | Done | Pitch in semitones relative to each speaker; speaker-adapted pitch range with a stability check |
| Never claim an unmeasured metric | Done | Every metric reports `measured`, `estimated` or `unavailable` |

### Temporal grounding

| Requirement | Status | Where |
| --- | --- | --- |
| Flaw intervals with start and end | Done | Every finding has a participant interval; the frontend shows it only when valid |
| Compare against a baseline | Done | Optional reference recording, compared over words recognised in both |
| Explanations tied to measurements and the reference | Done | Each finding has evidence, method, rule and thresholds |
| Low confidence and missing alignment identified | Done | Evidence quality, withheld rules with reasons, coverage warnings |

### Dashboard and visualisation

| Requirement | Status | Where |
| --- | --- | --- |
| Audio and transcript upload | Done | Workspace, with separate reference transcript |
| Playback, waveform, timeline | Done | Dashboard; jump to a word or finding |
| Baseline-versus-participant comparisons | Done | Findings, evidence tables, global comparison metrics |
| Highlighted flaw intervals | Done | Waveform bands for findings with valid intervals |
| Evidence, severity, confidence and limitations per finding | Done | Severity only where a tested magnitude rule supports it; evidence quality instead of a confidence score |
| 2D fallback for every WebGL view | Done | Acoustic Twin 2D view and data table |
| Dark theme, green accents, keyboard access, focus states, reduced motion | Done | Checked by tests and the end-to-end keyboard test |
| Supplied sample data only, never invented live metrics | Done | Demo fixture always labelled; real views show only backend results |

### Coach

| Requirement | Status | Where |
| --- | --- | --- |
| Actionable, evidence-backed coaching | Done | One suggestion per kind of finding, with per-finding measurements, intervals, a reason and a confirmed or uncertain label |
| Uses measured analysis and rubric retrieval | Partial | Uses measured findings; there is no separate rubric retrieval system. The rule templates are the rubric |
| Deterministic fallback when a language model is unavailable | Done | Deterministic rules are the only path; no language model is integrated, so nothing needs a key |
| No unsupported causal claims | Done | Wording tests ban causal and psychological claims |

### Technology, persistence, hosting, security

| Item | Status |
| --- | --- |
| React, Vite, TypeScript, Tailwind, React Router, WaveSurfer, Recharts, Three.js, React Three Fiber, Drei | Used |
| TanStack Query | Not used; the app has one analysis request and plain `fetch` suffices |
| FastAPI, Pydantic, NumPy, SciPy, librosa, Parselmouth, faster-whisper | Used |
| Vitest, React Testing Library, Playwright, pytest | Used |
| Supabase (optional) | Implemented for saving results; off without credentials; never run against a real project |
| Hosting on Vercel and Render | Prepared (`render.yaml`, `frontend/vercel.json`, `docs/DEPLOYMENT.md`); **not deployed** |
| `.env` ignored, placeholders only in examples, no secrets in `VITE_` variables | Checked; tests cover the examples and the health output |
| Upload type, size and duration validation; uploads not retained | Done |

## 3. Deliverables in the repository

| Deliverable | Location |
| --- | --- |
| Source code: backend and frontend | `backend/`, `frontend/` |
| Setup, usage, API and troubleshooting | `README.md`; interactive API docs at `/docs` when the backend runs |
| Specification and milestone record | `docs/PROJECT_SPEC.yaml`, `docs/MILESTONE_5_2_ACCEPTANCE.md` |
| Contrastive dataset, schema, validator and dataset card | `data/`, `backend/app/dataset/` |
| Evaluation scripts | `python -m app.detection.evaluate`, `python -m app.comparison.evaluate`, `python -m app.audio.evaluate_pitch` |
| Deployment guide | `docs/DEPLOYMENT.md` |
| Optional database schema | `docs/supabase/schema.sql` |
| Dataset publishing guide | `data/HOSTING.md` |
| Automated tests | `backend/tests/`, `frontend/src/**/*.test.ts(x)`, `frontend/e2e/` |

Not in the repository, and not produced by this work: a hosted demo, a published dataset, a demo video or slides, and any user study.

## 4. Known limitations

- Detection thresholds are project defaults checked on a small dataset of transformed recordings from three speakers; some were chosen on that same dataset. They have not been validated with listeners or natural speech.
- Filler counts are still lower bounds. An acoustic check now finds fillers the recogniser leaves out (16 of 24 synthetic fillers in the dataset, against 1 before), but it is tested only on synthetic fillers, misses short or breathy ones, and can mistake a held vowel for a filler, so its findings are worded as possible.
- Pitch variation cannot be judged for voices the tracker cannot follow stably, such as the dataset's low, creaky speaker; those findings are withheld. Choosing the speaker's pitch range from the opening seconds was measured (`python -m app.audio.evaluate_pitch`) and did not recover that voice without losing others or adding false readings, so it was not adopted.
- Word timing comes from speech recognition, accurate to about a tenth of a second; misrecognised words drop out of comparisons.
- Without a reference recording, pace and pauses are judged against general limits, and uneven pacing and pause placement are not judged at all.
- Dataset transcripts are unverified machine output until a person runs `python -m app.dataset transcripts review`; one source description is uncertain; the filler examples are synthetic sounds, not natural hesitations.
- Memory was measured on the development machine, not on Render: with `tiny` an analysis of a 60-second recording and reference peaked at 471 MB, so the blueprint uses `tiny` and a 60-second limit for the 512 MB free instance, with about 40 MB of headroom.

## 5. Actions only the owner can take

1. Deploy, following `docs/DEPLOYMENT.md`, and enter the settings it lists on Render and Vercel. Then update its status line.
2. Optionally create a Supabase project, run `docs/supabase/schema.sql`, and set the two Supabase variables on the backend.
3. Have a person listen to and verify the dataset transcripts with `python -m app.dataset transcripts review`.
4. Optionally publish the dataset following `data/HOSTING.md`, after confirming the licence reading in the dataset card.
5. Prepare any presentation material the hackathon requires.
