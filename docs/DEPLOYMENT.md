# Deploying SpeakIQ AI Coach

**Status: Not deployed.** Nothing has been deployed to any host. This guide and the configuration files `render.yaml` and `frontend/vercel.json` prepare for it. Update this line only after a deployment has actually been checked working.

The plan, from the project specification: the frontend on Vercel and the backend on Render. Either can be swapped for a compatible host.

## What you will need

- A Render account and a Vercel account, both connected to this GitHub repository.
- Optional: a Supabase project, only if you want saving analyses switched on.
- Optional: a Hugging Face token, only if you change the transcription model to a private or gated one.

None of these values belongs in Git, in a chat, or in a `VITE_` variable. Enter them in each host's dashboard.

## 1. Backend on Render

`render.yaml` is a Render blueprint. In Render, choose **New > Blueprint**, pick this repository, and Render reads the file.

| Setting | Value | Notes |
| --- | --- | --- |
| Root directory | `backend` | |
| Build command | `pip install -r requirements.txt && python -m app.speech.prefetch` | The second part downloads the transcription model during the build |
| Start command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` | Render provides `$PORT` |
| Health check path | `/api/health` | |

Environment variables (Render > the service > Environment):

| Variable | Set in the blueprint | What you enter |
| --- | --- | --- |
| `PYTHON_VERSION` | `3.13.7` | — |
| `APP_ENV` | `production` | — |
| `WHISPER_MODEL` | `tiny` | Fits the free instance's 512 MB. Use `base` on an instance with at least 1 GB (see Memory below) |
| `WHISPER_DEVICE` | `cpu` | — |
| `WHISPER_COMPUTE_TYPE` | `int8` | — |
| `WHISPER_DOWNLOAD_ROOT` | `models` | Keeps the model downloaded at build time inside the deployed service |
| `MAX_UPLOAD_MB` | `25` | — |
| `MAX_AUDIO_SECONDS` | `60` | Longest recording accepted. Memory grows with length; raise it only on a larger instance |
| `BACKEND_CORS_ORIGINS` | asks you | Your Vercel address, for example `https://your-app.vercel.app`. Without it the browser blocks every request |
| `SUPABASE_URL` | asks you | Optional. Leave empty to keep saving off |
| `SUPABASE_SERVICE_ROLE_KEY` | asks you | Optional secret. Leave empty to keep saving off |
| `HF_TOKEN` | asks you | Optional secret. Not needed for `tiny` or `base` |

After the first deploy, open `https://<your-service>.onrender.com/api/health`. It should report `"status": "ok"`, `"model": "tiny"`, and whether saving is configured.

### Things to check on Render

- **Memory.** The free instance has 512 MB of RAM. Peak memory of the backend process during one analysis of a recording plus a reference of the same length, measured on the development machine (Windows working set, which is close to, but not the same as, Linux resident memory):

  | Model | 25 s | 60 s | 90 s | 120 s | 180 s | 300 s |
  | --- | --- | --- | --- | --- | --- | --- |
  | `tiny` | 464 MB | 471 MB | 482 MB | 515 MB | 578 MB | 704 MB |
  | `base` | 560 MB | — | — | 583 MB | — | 752 MB |

  About 130 MB of this is the libraries, and the rest is the model and the analysis, which grows with the recording's length. `base` does not fit in 512 MB even for short recordings, so the blueprint uses `tiny` with a 60-second limit, which peaked at 471 MB: about 40 MB of headroom. This was measured on Windows, not on Render; if the service restarts during an analysis, lower `MAX_AUDIO_SECONDS` further or move to a larger instance. On an instance with at least 1 GB, `WHISPER_MODEL=base` and `MAX_AUDIO_SECONDS=300` fit (752 MB peak at 300 s). `tiny` recognises words less accurately than `base`. On the demonstration dataset (`python -m app.detection.evaluate` with `WHISPER_MODEL=tiny`) it reported the labelled flaw for 48 of 54 mild-to-severe samples against 45 with `base`, and found all 24 inserted synthetic fillers against 16, but gave 14 findings of another category against 12, and could not use the reference for 2 strongly filtered samples.
- **First request.** If the model was not downloaded at build time, the first analysis downloads it (about 75 MB for `tiny`, 145 MB for `base`) and is slow.
- **Python version.** Development used Python 3.14 on Windows. The full backend test suite also passes on a fresh Python 3.13 install on Windows (see `docs/FINAL_AUDIT.md`), which matches `PYTHON_VERSION` in the blueprint. Linux has not been tested.
- **Cold starts.** Free instances sleep when idle; the first request after a sleep takes longer.

## 2. Frontend on Vercel

In Vercel, choose **Add New > Project**, pick this repository, and set:

| Setting | Value |
| --- | --- |
| Root directory | `frontend` |
| Framework preset | Vite (also set in `frontend/vercel.json`) |
| Build command | `npm run build` |
| Output directory | `dist` |

Environment variable (Vercel > the project > Settings > Environment Variables):

| Variable | Value |
| --- | --- |
| `VITE_API_BASE_URL` | Your Render backend address, for example `https://speakiq-ai-coach-api.onrender.com`, without a trailing slash |

`VITE_` values are compiled into the public JavaScript at build time, so redeploy the frontend after changing it, and never put a secret in one. `frontend/vercel.json` sends every route to the app, so refreshing `/dashboard` works.

## 3. Optional: saving analyses with Supabase

1. In your Supabase project's SQL editor, run `docs/supabase/schema.sql`.
2. In Render, set `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` (Supabase > Project Settings > API). Use the service-role key, not the anon key; it stays on the backend.
3. Redeploy the backend. `/api/health` should report `"persistence": {"configured": true}`.

## 4. After deploying: check it

1. `GET https://<backend>/api/health` returns `"status": "ok"`.
2. Open the Vercel address. The footer should say **Backend online**. If it says **Backend not reachable**, check `VITE_API_BASE_URL` on Vercel and `BACKEND_CORS_ORIGINS` on Render.
3. In the workspace, analyse a short WAV file and open the dashboard.
4. Refresh the dashboard page; it should load rather than show a 404.
5. Only then update the status line at the top of this file.

## Order

Deploy the backend first so you know its address, set `VITE_API_BASE_URL` on Vercel and deploy the frontend, then set `BACKEND_CORS_ORIGINS` on Render to the Vercel address and redeploy the backend.
