# SpeakIQ AI Coach

Evidence-first speech delivery analysis with temporally grounded explanations, built for the track **Contrastive Speech Analytics & Temporal Flaw Grounding**.

The full specification lives in [`docs/PROJECT_SPEC.yaml`](docs/PROJECT_SPEC.yaml) and is the source of truth for every milestone.

## Status

| Area | State |
| --- | --- |
| Backend `GET /health` | Working |
| Frontend app shell | Working |
| Audio analysis, transcription, alignment | Not implemented yet |
| Supabase, LLM provider, hosting | Not connected |

No paid API keys are needed to run the project locally.

## Repository layout

```
frontend/   React + Vite + TypeScript + Tailwind CSS
backend/    Python + FastAPI
docs/       Project specification
```

## Prerequisites

- Node.js 20 or newer (developed on 24) and npm
- Python 3.11 or newer (developed on 3.14)

## Environment setup

Configuration is optional; the defaults work for local development.

```powershell
Copy-Item .env.example .env
```

| Variable | Used by | Default | Purpose |
| --- | --- | --- | --- |
| `APP_ENV` | backend | `development` | Reported by `/health` |
| `BACKEND_CORS_ORIGINS` | backend | `http://localhost:5173,http://127.0.0.1:5173` | Browser origins allowed to call the API |
| `VITE_API_BASE_URL` | frontend | `http://localhost:8000` | Where the frontend finds the API |

`.env` is ignored by Git. `VITE_*` values are compiled into the public client bundle, so never put a secret in one.

## Backend

From `backend/` (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
```

On macOS or Linux, activate with `source .venv/bin/activate` instead.

- Health check: http://localhost:8000/health
- Interactive API docs: http://localhost:8000/docs
- Tests: `pytest`

## Frontend

From `frontend/`:

```powershell
npm install
npm run dev
```

- App: http://localhost:5173
- Tests: `npm test`
- Production build: `npm run build` (output in `frontend/dist/`)

Run the backend and the frontend in two separate terminals. The frontend shows whether it can reach the backend.
