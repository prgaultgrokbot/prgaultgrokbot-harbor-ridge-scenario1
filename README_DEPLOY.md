# Harbor Ridge — Capstone Scenario 1, standalone cloud edition

This folder is a complete, standard-library-only Python web application for a
**Render Free Web Service**. It needs no n8n, database, pip packages, tunnel,
laptop server, or AI key. Python 3.10+ is required; the blueprint pins 3.12.12.

## What the Coordinator gets

- Original branded demo hub at `/`, executive dashboard at `/api/scoreboard`,
  and 32 fictional sample emails at `/api/samples`.
- A bundled snapshot of the original audit log, recalculated on every scoreboard
  request using the original `live_scoreboard` calculation, not hard-coded metrics.
- Lightweight triage form: **Replay reference sample** replays a previously
  observed Gemini prediction into this instance's log. This is explicitly marked
  recorded replay, NOT a new AI prediction and NOT an expected-label shortcut.
- **Load labelled test set** replays all 32 recorded predictions without API calls.
  Repeated activity counts again, exactly as in the original scoreboard.
- Human review queue and Accept/Correct forms work entirely in Python. Review
  decisions are separate from original prediction records and do not rewrite
  measured accuracy. Replaying an item after review makes it pending again.
- `/teaching` lists the original `teach/` and `teaching_source/` files and provides
  a downloadable source ZIP at `/harbor_ridge_teaching_source.zip`.
- Optional FNOL remains a **source-only walkthrough**; running that extension and
  arbitrary original n8n webhooks still requires the original n8n lab.
- No emails are sent. This is an intentionally shared, fictional training sandbox,
  not a production app, identity system, or private intern workspace.

The original source copies in teaching folders may mention local paths or n8n:
those are inert teaching downloads, not runtime dependencies. `cloud_server.py`
is the runnable cloud adaptation shown alongside them. All runtime assets and
initial data live under this folder; no `/workspace` paths are used at runtime.

## Verify locally (without disturbing the original service on 8787)

```bash
cd /workspace/capstones/scenario1_cloud
python3 verify.py
```

The test copies the entire app into a temporary folder, starts `python3 server.py`
on a random unused local port, verifies **HTTP 200 for `/`**, tests APIs, all four
panels, source downloads, no-key AI behavior, recorded replay, human review,
labelled-batch replay and safety limits, then stops its own test server. It does
not alter the bundled audit log or the original demo on 8787.

For an interactive local check:

```bash
cd /workspace/capstones/scenario1_cloud
PORT=8788 python3 server.py
# In another terminal:
curl -i http://127.0.0.1:8788/
```

Open `http://127.0.0.1:8788/`. Stop with Ctrl-C. If no other app uses port 8787,
plain `python3 server.py` defaults to 8787. The server always binds `0.0.0.0` and
honors the host's `PORT` environment variable.

## Exact Render Free deployment steps

Render deploys Python services from a Git repository, **not a ZIP upload**.
The ZIP is a transfer artifact; unpack it before adding files to a repository.
Publishing the repository and creating the cloud service are separate steps;
this package has NOT already been deployed and does NOT contain a public URL.

1. Unzip `harbor_ridge_cloud.zip`. Put the **contents of `scenario1_cloud/`** at
   the root of a new GitHub, GitLab or Bitbucket repository (or use a dedicated
   subfolder in an existing repo and set Render's Root Directory to it). Include
   `data/`, `static/`, `teach/`, `teaching_source/`, and the top-level files.
   Do not upload any `.env`, passwords, API keys, or unrelated local logs.
2. Sign in at https://dashboard.render.com/ and choose **New → Web Service**.
   Connect the repository/branch. A supported public Git repository URL also
   works via Render's public-repository option when offered.
3. Use these settings:

   | Setting | Value |
   |---|---|
   | Name | `harbor-ridge-scenario1` (or an available variant) |
   | Language / Runtime | **Python 3** |
   | Root Directory | blank if files are at repo root; otherwise the subfolder |
   | Build Command | `echo "Standard-library app: no pip dependencies"` |
   | Start Command | `python3 server.py` |
   | Instance Type / Compute plan | **Free — $0** |
   | Health Check Path | `/healthz` |

4. Set `PYTHON_VERSION=3.12.12` and `PYTHONUNBUFFERED=1` under Environment.
   Do **not** set `PORT` yourself on Render; it supplies the port automatically.
   Leave `GEMINI_API_KEY` unset for a completely key-free reference walkthrough.
5. Click **Deploy Web Service**. Wait for the deploy logs to say the service is
   live. Visit the exact HTTPS URL Render displays, usually
   `https://harbor-ridge-scenario1.onrender.com` or an available name variant.
   This is an **expected URL pattern, not a link already created**.
6. Verify `/`, `/healthz`, `/api/scoreboard`, `/teaching`, the triage panel's
   recorded-sample replay, and the review queue. Share the displayed root URL
   with Richard Buffalo. He only needs a browser; no n8n or Render login is
   required to open this intentionally public demo.

Alternative: use **New → Blueprint** against a repository with the included
`render.yaml` at its root. It selects `plan: free`, the same no-op build command,
start command and health check automatically. Check the plan remains Free before
confirming. `Procfile` is included as an additional launch hint.

**No pip is needed; there is deliberately no requirements.txt.** The build step
is a harmless echo, not an install.

## Free-tier behavior and cost guardrails

- Render's published Free tier needs no credit card for this deployment. Choose
  Free and do not add payment details or accept any paid upgrade. If account
  verification unexpectedly requests a card, stop rather than entering one.
- Free web services sleep after **15 minutes without inbound traffic**, then
  wake on the next visit. The first visitor may see a loading page for about a
  minute. The dashboard polls while open, so close the tab when finished.
- Filesystem changes are **ephemeral**: sleep, restart or redeploy can reset all
  new cloud triage/review records to the bundled snapshot. The local original
  lab is unaffected. This does not offer durable multi-intern submissions.
- Free workspace hours, bandwidth and build-minute limits apply. The current
  documentation lists 750 free instance hours per workspace per calendar month.
  With no payment method, hitting usage limits can suspend service/builds rather
  than buying more capacity. Do not add payment details to bypass a free limit.
- This app has no user login: anyone who has or discovers the public URL can view
  fictional samples, replay results and record sandbox review decisions. Use
  only the bundled fictional training data. No ServiceNow credentials are used.
- Each local audit/decision log is capped at about 5 MB; redeploy resets training
  data if that cap is reached. This is a small demo, not a hardened production
  server. There is no persistent volume or paid database.

Render sources checked for this package:
https://render.com/docs/free
https://render.com/docs/your-first-deploy
https://render.com/docs/web-services
https://render.com/articles/platforms-with-a-real-free-tier-for-developers-in-2026

## Optional live Gemini (not needed for the Coordinator walkthrough)

Set these ONLY if you deliberately want new AI predictions:

| Environment variable | Meaning |
|---|---|
| `GEMINI_API_KEY` | Optional server-side API key; never included in this package or browser HTML |
| `GEMINI_MODEL` | Optional model ID; defaults to `gemini-3.1-flash-lite`, matching the reference lab |
| `MAX_AI_CALLS_PER_HOUR` | Optional shared process-wide limit; defaults to `20`; `0` disables calls |

Without a key, submitting custom email text gives a clear graceful notice;
no prediction is invented and nothing is logged. Recorded replay works regardless.
With a key, only an explicit **Run live Gemini triage** submission calls the
Gemini REST API using stdlib `urllib`; it validates team, confidence and complaint
fields, applies human review at confidence <0.8 or complaint=true, and appends
successful results to the cloud audit log. No other action calls the AI API.
All data entered in this form must be fictional and is sent to Google when AI
is requested. Provider/model errors leave the hub working and do not log a fake
result. New live predictions are unlabelled: activity counts update, measured
accuracy continues to use labelled rows only.

Model availability and API quotas vary by account. A Render Free service does
**not** make Gemini usage free. Keep the key unset to guarantee this app makes no
billable model requests. The hourly cap is a modest demo safeguard, resets with
the process, and is not a billing guarantee. Live external Gemini was not called
while packaging; the REST integration is tested with a stubbed response only.
