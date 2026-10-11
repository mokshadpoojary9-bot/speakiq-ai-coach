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

## Commands

Frontend (run from `frontend/`):

- `npm install`
- `npm run dev` — dev server on http://localhost:5173
- `npm test` — Vitest
- `npm run build` — type-check and production build

Backend (run from `backend/`, PowerShell):

- `python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -r requirements-dev.txt`
- `uvicorn app.main:app --reload --port 8000`
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
