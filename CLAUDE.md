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
- `data/` — dataset (not created yet)
- `backend/app/audio/` — real feature extraction (`loading`, `features`, `pitch`, `timing`, `pipeline`, `schemas`). Each metric reports `status` (`measured` / `estimated` / `unavailable`), `method` and `limitations`; keep that contract for new metrics.
- `backend/app/speech/` — local transcription (faster-whisper, loaded lazily) and transcript-to-recognition word alignment. Unmatched words get null times; never interpolate or invent them.
- API routes live under `/api` in `backend/app/main.py`: `health`, `features`, `transcribe`, `align`, `analyze`. Errors are `{"detail": {"code", "message"}}`. The frontend calls `/api/health` and `/api/analyze` through `frontend/src/lib/api.ts`.

## Configuration and secrets

- Backend config: `backend/.env` (ignored), documented in `backend/.env.example`. `HF_TOKEN` is optional (the default public Whisper model needs none), backend-only, excluded from `Settings` repr, and must never be logged, returned by the API, or placed in any `VITE_*` variable.
- Frontend config: `frontend/.env.local` (ignored) holds only `VITE_API_BASE_URL`; read it through `frontend/src/lib/api.ts` rather than hardcoding URLs.
- Backend tests must stay offline: use the fakes in `backend/tests/speech_fakes.py` instead of loading a real model.
- Windows: `app/_windows_runtime.py` preloads a current `msvcp140.dll` (from the `msvc-runtime` package) before native imports; without it ctranslate2 segfaults on machines with an old system C++ runtime. Keep that import first in `app/__init__.py`.

The frontend has two data sources. A real analysis from `/api/analyze` lives in `frontend/src/lib/session.tsx` (memory only) and is shown with `LiveBadge` on the Dashboard and Acoustic Twin. Everything else comes from `frontend/src/fixtures/demoAnalysis.ts`, hand-authored demo data that must keep `isDemo: true` and a `DemoBadge`. Never mix the two in one view, and never show findings, baselines or coaching for a real recording until the backend produces them. Frontend tests mock `fetch` (see `frontend/src/test/analysisSample.ts`); they must not need a running backend.

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
