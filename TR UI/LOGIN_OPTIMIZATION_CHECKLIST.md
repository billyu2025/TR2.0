# Login Optimization Checklist

Use this checklist to improve login performance and reliability under concurrent usage.

## Tracking Fields

- Status: `todo` / `in_progress` / `done`
- Owner: person responsible
- Due Date: target date (`YYYY-MM-DD`)

---

## A. Bottleneck Identification (Do First)

| Item | Status | Owner | Due Date |
|---|---|---|---|
| Add segmented timing logs in login API: `db_query_ms`, `password_verify_ms`, `token_issue_ms`, `total_ms` | todo |  |  |
| Attach `request_id` to login logs for Nginx/backend correlation | todo |  |  |
| Measure 24h login success rate, timeout rate, p50/p95/p99 | todo |  |  |
| Classify login failures: `401` / `429` / `5xx` / timeout | todo |  |  |
| Record login endpoint QPS and slow-request ratio during load tests | todo |  |  |

## B. Frontend / Client Behavior

| Item | Status | Owner | Due Date |
|---|---|---|---|
| Reuse token if valid; avoid repeated login per operation | todo |  |  |
| Re-login only on `401`, not before every request | todo |  |  |
| Add clear error messages: wrong credential / session invalid / timeout | todo |  |  |
| Apply exponential backoff on login retry (max 2-3 retries) | todo |  |  |
| Add login mutex to prevent concurrent duplicate login calls | todo |  |  |

## C. Backend Login Path

| Item | Status | Owner | Due Date |
|---|---|---|---|
| Keep login API path minimal (auth + token issuance only) | todo |  |  |
| Move non-critical work out of login request path | todo |  |  |
| Ensure single-session invalidation is O(1), no wide scans | todo |  |  |
| Set explicit login API timeout guard (e.g., 5-10s) | todo |  |  |
| Standardize login response fields: `code`, `message`, `request_id` | todo |  |  |

## D. Database / Storage

| Item | Status | Owner | Due Date |
|---|---|---|---|
| Ensure index exists on login lookup field (e.g., `username`) | todo |  |  |
| Reduce transaction scope for login writes | todo |  |  |
| Review SQLite lock wait (`busy_timeout`) and lock contention | todo |  |  |
| Avoid writing non-essential fields during login | todo |  |  |
| Optional: move session/token state to Redis to reduce DB write contention | todo |  |  |

## E. Runtime / Gateway (Nginx + App Workers)

| Item | Status | Owner | Due Date |
|---|---|---|---|
| Tune app worker count according to CPU and workload | todo |  |  |
| Isolate login and heavy download paths (process/queue isolation) | todo |  |  |
| Enable and tune upstream keepalive in Nginx | todo |  |  |
| Review proxy timeout settings for connect/read/send | todo |  |  |
| Check connection queue and file descriptor limits | todo |  |  |

## F. Security / Stability Controls

| Item | Status | Owner | Due Date |
|---|---|---|---|
| Add rate limit for login (IP + username dimensions) | todo |  |  |
| Add temporary lock policy for repeated failures | todo |  |  |
| Validate password hash cost settings for latency/safety balance | todo |  |  |
| Add alerts for login failure spikes and timeout spikes | todo |  |  |
| Prevent unlimited retries causing retry storms | todo |  |  |

## G. Validation and Acceptance

| Item | Status | Owner | Due Date |
|---|---|---|---|
| Run login-only load test at 10/20/30 VUs | todo |  |  |
| Run mixed login + download load test | todo |  |  |
| Run 30-60 minute soak test | todo |  |  |
| Verify acceptance target: login success rate >= 99% | todo |  |  |
| Verify acceptance target: login timeout rate <= 1% | todo |  |  |
| Verify acceptance target: login p95 <= 1s (LAN) or <= 2s (WAN) | todo |  |  |

## H. Suggested Execution Order for This Project

| Step | Status | Owner | Due Date |
|---|---|---|---|
| 1) Update load script to reuse token per VU (re-login on 401 only) | todo |  |  |
| 2) Add segmented login timing logs | todo |  |  |
| 3) Add/check username index and reduce login transaction scope | todo |  |  |
| 4) Tune worker and Nginx timeout/keepalive settings | todo |  |  |
| 5) Re-run 20/30 VU tests and compare before/after metrics | todo |  |  |

---

## I. Actionable Runbook (Directly Executable)

This section is the hands-on procedure for this project. Execute from `C:\TR-master\TR UI`.

### I-1. Pre-check (15 min)

| Action | Command / Operation | Expected Output | Status | Owner | Due Date |
|---|---|---|---|---|---|
| Confirm login endpoint | `POST /api/auth/login` in backend route | Endpoint confirmed | todo |  |  |
| Confirm test script exists | `k6_download_concurrency.js` in project root | Script found | todo |  |  |
| Confirm k6 installed | `k6 version` | k6 version shown | todo |  |  |
| Confirm app startup | Start backend service and open login page | Login page reachable | todo |  |  |

### I-2. Backend login timing instrumentation (A1)

Add timing points in `backend/tr_fill_in_api.py` inside `login()`:
- `db_query_ms`: user lookup and related DB read time
- `password_verify_ms`: `_verify_password(...)` time
- `token_issue_ms`: `_create_session(...)` time
- `total_ms`: full request time

Recommended log event format (single line JSON):

```json
{
  "event": "login_attempt",
  "request_id": "uuid",
  "username": "masked_or_internal_username",
  "status_code": 200,
  "result": "success",
  "fail_type": "",
  "db_query_ms": 12,
  "password_verify_ms": 35,
  "token_issue_ms": 8,
  "total_ms": 60
}
```

Acceptance:
- Every login request writes one structured log line.
- All 4 timing fields are present on both success and failure paths (failure can use `0` for missing segments).

| Item | Status | Owner | Due Date |
|---|---|---|---|
| Add timing points in login API | todo |  |  |
| Add structured login log line | todo |  |  |
| Verify all login branches emit timing fields | todo |  |  |

### I-3. Request correlation with `request_id` (A2)

Implementation checklist:
- Read `X-Request-ID` from request header; if missing, generate UUID.
- Put value in request context and include it in login logs.
- Return `X-Request-ID` in response header.
- Ensure Nginx access log includes request id field.

Acceptance:
- Randomly pick one login call and trace it in both Nginx and backend logs by the same `request_id`.

| Item | Status | Owner | Due Date |
|---|---|---|---|
| Add request_id generation/propagation | todo |  |  |
| Return request_id in response header | todo |  |  |
| Include request_id in Nginx access logs | todo |  |  |

### I-4. 24h baseline observation (A3/A4)

Metrics to collect (rolling 24h):
- `login_total`
- `login_success`
- `login_timeout`
- `login_401`, `login_429`, `login_5xx`
- `total_ms_p50`, `total_ms_p95`, `total_ms_p99`

Definitions:
- success rate = `login_success / login_total`
- timeout rate = `login_timeout / login_total`
- failure breakdown = `401 / 429 / 5xx / timeout`

Acceptance:
- One complete 24h report with no missing hour bucket.
- Failure categories sum to total failures.

| Item | Status | Owner | Due Date |
|---|---|---|---|
| Start 24h log collection | todo |  |  |
| Produce baseline metrics table | todo |  |  |
| Produce failure classification table | todo |  |  |

### I-5. Load-test execution (A5)

Run from PowerShell at project root:

```powershell
# 1) login/download mixed pressure (existing template script)
k6 run .\k6_download_concurrency.js -e BASE_URL=http://127.0.0.1:8000 -e MODE=dd_no -e ORDER_NOS=134396,134321,137351,137697 -e USERS=10 -e DURATION=10m

# 2) same case at higher concurrency
k6 run .\k6_download_concurrency.js -e BASE_URL=http://127.0.0.1:8000 -e MODE=dd_no -e ORDER_NOS=134396,134321,137351,137697 -e USERS=20 -e DURATION=10m

# 3) stress checkpoint
k6 run .\k6_download_concurrency.js -e BASE_URL=http://127.0.0.1:8000 -e MODE=dd_no -e ORDER_NOS=134396,134321,137351,137697 -e USERS=30 -e DURATION=10m
```

During each run, record:
- login QPS (or request rate)
- login timeout count/rate
- login `http_req_duration` p50/p95/p99
- slow ratio (`total_ms > 1000ms` and optionally `> 2000ms`)

Acceptance:
- Three comparable result snapshots (10/20/30 users).
- Clear curve showing where p95 or timeout starts rising sharply.

| Item | Status | Owner | Due Date |
|---|---|---|---|
| Run 10-user test | todo |  |  |
| Run 20-user test | todo |  |  |
| Run 30-user test | todo |  |  |
| Export comparison table | todo |  |  |

### I-6. Result template (fill after runs)

| Scenario | Users | Duration | Login Success Rate | Timeout Rate | p50 (ms) | p95 (ms) | p99 (ms) | 401 | 429 | 5xx | Slow Ratio (>1s) | Notes |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Baseline | 10 | 10m |  |  |  |  |  |  |  |  |  |  |
| Medium | 20 | 10m |  |  |  |  |  |  |  |  |  |  |
| High | 30 | 10m |  |  |  |  |  |  |  |  |  |  |

### I-7. Go/No-Go criteria

Use these criteria before moving to optimization phase:
- Login success rate >= `99%`
- Login timeout rate <= `1%`
- Login p95 <= `1000ms` (LAN) or <= `2000ms` (WAN)
- No unexplained 5xx bursts

If any criterion fails, prioritize fixes in this order:
1) client token reuse and duplicate-login control  
2) login API path simplification and timing hot spots  
3) DB index/lock contention  
4) worker + gateway timeout/keepalive tuning
