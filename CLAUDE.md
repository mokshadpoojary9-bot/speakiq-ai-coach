# CLAUDE.md

## Project

SpeakIQ AI Coach — evidence-first speech delivery analysis with temporally grounded explanations, for the track "Contrastive Speech Analytics & Temporal Flaw Grounding".

- `docs/PROJECT_SPEC.yaml` is the source of truth. Read it before starting any milestone. Do not ask the owner to locate a spec file elsewhere.
- This is **not** EvidenceLoop (`C:\Users\HP\Desktop\evidenceloop`). Never reuse, overwrite, switch to, or push to that repository.
- Implement one milestone at a time and preserve working features.

## Non-negotiable product rules

- Every detected flaw is tied to a specific audio interval (times in seconds, `start < end`).
- Distinguish measured facts, inferred explanations, and unavailable evidence.
- Never invent analysis metrics or present demo data as live. Demo fixtures must be visibly labelled.
- Every essential WebGL visualization has an accessible 2D fallback.
- No paid API is required for local development. Do not add Supabase, LLM, NVIDIA, Nebius, Vercel or Render integrations until a milestone explicitly calls for them.
- Never put secrets in frontend environment variables (`VITE_*` values are public).

## Layout

- `frontend/` — React + Vite + TypeScript + Tailwind CSS
- `backend/` — Python + FastAPI
- `docs/` — specification and documentation
- `data/` — contrastive dataset: `sources/` (3 committed LibriVox clips + `sources.json`), `examples/` (7 committed samples), `speakiq-contrastive-v1/manifest.json` (committed; its `audio/` is gitignored and rebuilt), `schema/`, `DATASET_CARD.md`
- `backend/app/dataset/` — schema (pydantic, versioned), deterministic transforms, `build`, `validate`. Labels are known by construction; `measured` values are automatic estimates and must never be used to set labels. After changing the schema or recipes, rerun `export-schema`, `build` and `build-examples` and update the figures in the dataset card from the new manifest. Praat resynthesis must stay seeded (`PRAAT_SEED`) or builds stop being reproducible.
- `backend/app/audio/` — real feature extraction (`loading`, `features`, `pitch`, `timing`, `pipeline`, `schemas`). Each metric reports `status` (`measured` / `estimated` / `unavailable`), `method` and `limitations`; keep that contract for new metrics.
- `backend/app/speech/` — local transcription (faster-whisper, loaded lazily) and transcript-to-recognition word alignment. Unmatched words get null times; never interpolate or invent them.
- `backend/app/comparison/` — reference-versus-participant comparison. Reports measured differences only (global metrics, and timing differences between words aligned in both recordings). It reports differences only; findings come from `app/detection`.
- `backend/app/detection/` — signal quality, alignment status and rule-based findings (`rules.py`, thresholds in `schemas.py: DetectionSettings`). Each rule must end as `triggered`, `not_triggered`, `withheld` (with a reason) or `not_supported`; withhold rather than guess. Severity is only given by the two reference-based magnitude rules. `coaching.py` holds fixed templates keyed by rule and category; a tip must quote findings and must never exist without one. `python -m app.detection.evaluate` tabulates behaviour on the dataset; rerun it and update the README table after changing a rule or threshold.
- API routes live under `/api` in `backend/app/main.py`: `health`, `features`, `transcribe`, `align`, `analyze` (main route; optional `reference` file), `compare`. Do not add another analysis route. Errors are `{"detail": {"code", "message"}}`. The frontend calls `/api/health` and `/api/analyze` through `frontend/src/lib/api.ts`.

## Measurement rules

- Pitch is tracked in two passes with a speaker-adapted range, plus a stability pass (`audio/pitch.py`). Report `reliability: low` rather than a confident number when octave jumps, too little voicing or an unstable result are seen; pitch rules are then withheld. Compare pitch only in semitones relative to the speaker.
- Do not add an articulation or clarity rule based on recognition errors or spectral measures: they penalise accent, voice and microphone.
- Transcripts in API responses: `human_verified` stays false. `review_status: user_attested` is only ever the sender's own statement about text they supplied; never set it for machine-generated text. On the shared transcript it means attested for both recordings; `attested_for` lists which.
- Do not filter compared words by recogniser probability: it was tried and measurably worsened results on the dataset (one fewer correct finding, two more off-label).
- Pause detection uses `PauseSettings` (`audio/features.py`): a relative threshold in quiet recordings and a noise-floor threshold in noisy ones; `unavailable` when speech cannot be separated from the background.
- Clipping is measured on decoded samples before mono mixing or resampling (`audio/loading.py`), with verdicts `detected`, `not_detected` or `uncertain`.
- Dataset transcripts stay `automatic_asr_unverified` until a named human reviewer records a review with `transcripts verify --listened`. Never run that command on the user's behalf or edit review fields by hand.
- The dataset is not published. Do not say it is unless an upload has actually succeeded; `data/HOSTING.md` holds the status line.

## Configuration and secrets

- Backend config: `backend/.env` (ignored), documented in `backend/.env.example`. `HF_TOKEN` is optional (the default public Whisper model needs none), backend-only, excluded from `Settings` repr, and must never be logged, returned by the API, or placed in any `VITE_*` variable.
- Frontend config: `frontend/.env.local` (ignored) holds only `VITE_API_BASE_URL`; read it through `frontend/src/lib/api.ts` rather than hardcoding URLs.
- Backend tests must stay offline: use the fakes in `backend/tests/speech_fakes.py` instead of loading a real model.
- Windows: `app/_windows_runtime.py` preloads a current `msvcp140.dll` (from the `msvc-runtime` package) before native imports; without it ctranslate2 segfaults on machines with an old system C++ runtime. Keep that import first in `app/__init__.py`.

The frontend has two data sources. A real analysis from `/api/analyze` lives in `frontend/src/lib/session.tsx` (memory only) and is shown with `LiveBadge` on the Dashboard and Acoustic Twin. Everything else comes from `frontend/src/fixtures/demoAnalysis.ts`, hand-authored demo data that must keep `isDemo: true` and a `DemoBadge`. Never mix the two in one view. For a real recording show only what the backend returned: findings and rules (`FindingsPanel`), suggestions (`RealCoach`) and the report (`RealReport`). Never write coaching text in the frontend. Frontend tests mock `fetch` (see `frontend/src/test/analysisSample.ts`); they must not need a running backend.

## Commands

Frontend (run from `frontend/`):

- `npm install`
- `npm run dev` — dev server on http://localhost:5173
- `npm test` — Vitest
- `npm run build` — type-check and production build
- `npm run test:e2e` — build, then Playwright against installed Edge (verifies the real WebGL scene)

Backend (run from `backend/`, PowerShell):

- `python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -r requirements-dev.txt`
- `uvicorn app.main:app --reload --port 8000` — API on http://127.0.0.1:8000, Swagger UI at `/docs`
- `python -m app.speech.prefetch` — download the transcription model once
- `python -m app.dataset build | build-examples | validate DIR | check | export | export-schema | transcripts status|sheet|verify` — dataset commands. `check` must pass before committing dataset changes.
- `pytest`

## Automatic GitHub Commit and Push Policy

Intended repository: `https://github.com/mokshadpoojary9-bot/speakiq-ai-coach` (remote `origin`), branch `main`.

- Automatically create meaningful milestone commits and push them to the existing intended GitHub repository after each completed milestone.
- Do not ask for approval before every routine milestone commit or push.
- Before committing, inspect the Git diff and ensure relevant tests and builds pass.
- Never commit `.env` files, API keys, passwords, tokens, private data, or other secrets.
- Verify the Git remote and current branch before pushing. Push only to the intended repository and branch.
- Never force-push, rewrite shared history, or overwrite unrelated user work.
- If authentication fails, the remote is ambiguous, tests fail, or unexpected changes could be lost, stop and report the problem.
- After each successful push, report the commit hash, milestone, tests run, and push status.
- Never claim a commit or push succeeded unless Git confirms it.
