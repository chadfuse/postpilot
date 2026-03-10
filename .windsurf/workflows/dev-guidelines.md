---
description: Development guidelines and checklist for implementing features and fixes
---

# PostPilot Development Guidelines

## Workflow: Implement → Test → Fix → Confirm

Every code change MUST follow this loop before being considered done:

### 1. Plan
- Identify the exact files and functions to change
- Check existing tests and related code for side effects
- Draft a concise plan with `todo_list`

### 2. Implement
- Make minimal, focused edits — prefer editing over rewriting
- Follow existing code style (indentation, naming, patterns)
- Add imports at the top of the file only
- Never hardcode secrets or credentials in source files
- Credentials priority: env vars → config.json → error

### 3. Test
- **Unit test** the change locally before declaring done:
  - API endpoints: `curl` the endpoint and verify JSON response
  - Database methods: call method and check DB state
  - Dashboard UI: load the page and verify no errors
  - Worker tasks: enqueue a job and check logs for success/failure
- **Integration test** for cross-component changes:
  - Scrape → verify videos in DB
  - Download → verify file exists and DB updated
  - Post → verify Facebook API response and DB `posted=TRUE`
  - Config change → verify all consumers read new value

### 4. Fix Loop
- If any test fails:
  - Read error logs: `curl http://localhost:8000/logs?limit=20`
  - Identify root cause (don't fix symptoms)
  - Fix the code
  - Re-run the SAME test
  - Repeat until passing

### 5. Confirm
- Run the full verification checklist (below)
- Only then mark the task as completed

---

## Pre-Change Checklist

- [ ] Read the target file(s) before editing
- [ ] Check if the function/endpoint already exists
- [ ] Verify imports are present

## Post-Change Checklist

- [ ] API restarted if `app/api.py` changed
- [ ] Worker restarted if `app/worker.py`, `app/poster.py`, `app/downloader.py`, or `app/scraper.py` changed
- [ ] Streamlit auto-reloads — just refresh browser
- [ ] No `DuplicateWidgetID` errors (unique `key=` on all st.button/st.input)
- [ ] No 422/500 errors on API calls (check Streamlit page for red errors)
- [ ] Credentials read from `get_facebook_credentials()` not raw `os.getenv()`
- [ ] Config changes saved to `config.json` AND `.env` if env var exists

## Service Restart Commands

```bash
# API
ps aux | grep uvicorn | grep -v grep | awk '{print $2}' | xargs kill 2>/dev/null
sleep 1
OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES python3 -m uvicorn app.api:app --host 0.0.0.0 --port 8000

# Worker
// turbo
ps aux | grep run_worker | grep -v grep | awk '{print $2}' | xargs kill 2>/dev/null
sleep 1
OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES python3 run_worker.py

# Dashboard
streamlit run dashboard/streamlit_app.py --server.port 8501
```

## Verification Commands

```bash
# Check API is up
curl -s http://localhost:8000/stats | python3 -c "import sys,json; print(json.load(sys.stdin)['success'])"

# Check worker is running
ps aux | grep run_worker | grep -v grep

# Check recent logs for errors
curl -s "http://localhost:8000/logs?limit=10" | python3 -c "import sys,json; [print(f\"{l['created_at']} [{l.get('type','?')}] {l['message']}\") for l in json.load(sys.stdin)['logs']]"

# Check Facebook token validity
curl -s "http://localhost:8000/facebook/stats"

# Check queue status
curl -s "http://localhost:8000/tasks/status" | python3 -c "import sys,json; d=json.load(sys.stdin); [print(f'{q}: pending={i[\"pending\"]} failed={i[\"failed\"]}') for q,i in d['queues'].items()]"
```

## Architecture Quick Reference

| Component | File | Port | Reads credentials from |
|-----------|------|------|----------------------|
| API | `app/api.py` | 8000 | `get_facebook_credentials()` → env → config.json |
| Worker | `app/worker.py` | — | `_get_config()` → config.json, env fallback |
| Poster | `app/poster.py` | — | Receives token as parameter from caller |
| Dashboard | `dashboard/streamlit_app.py` | 8501 | Calls API only |
| Config | `config/config.json` | — | Central config store |
| Secrets | `.env` | — | Loaded by python-dotenv at startup |

## DO NOT

- Run `git` unless user explicitly asks
- Start services without killing existing ones first
- Hardcode tokens in source files
- Skip the test step
- Declare done without verifying
