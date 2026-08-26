# Distributed Media Processing Microservice

An event-driven backend microservice: accepts a job request, hands the client a scoped
presigned S3 upload, processes the media (resize/compress for images; transcode/thumbnail
for video) via Celery workers once uploaded, gates the output through a content-moderation
check, and serves the result via CDN.

## Status

All four CI gates pass and are enforced, not aspirational:

| Gate | Result |
|---|---|
| Tests | 39/39 passing, 90% coverage |
| Lint (`ruff`) | Clean |
| Types (`mypy --strict`) | Clean, zero exceptions |
| Dependency audit (`pip-audit`) | Clean |

Before treating this as production-ready, read **`DECISIONS_NEEDED.md`** — six items
(cloud target, moderation vendor, API key storage, log shipping, quarantine retention,
CI deploy stage) are deliberately left as stubbed interfaces or working defaults pending a
human decision, not oversights.

## Quick start (local, Docker)

```bash
cp .env.example .env
# Fill in RABBITMQ_DEFAULT_USER/PASS and REDIS_PASSWORD at minimum — the stack refuses
# to start with empty values for those (docker-compose.yml enforces this).

cd infra
docker-compose up --build
```

API available at `http://localhost:8000`. RabbitMQ and Redis are internal-network-only —
by design (see the security audit history below), not reachable from the host.

## Quick start (local, no Docker — for development)

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env   # fill in at least VALID_API_KEYS for local testing

uvicorn app.main:app --reload
```

Celery worker (separate terminal, needs a real RabbitMQ/Redis reachable via `.env`):
```bash
celery -A app.celery_app worker --loglevel=info
```

## Running the checks yourself

```bash
ruff check app/
mypy --strict app/
pytest tests/ --cov=app --cov-report=term-missing
pip-audit -r requirements.txt
```

The test suite needs `ffmpeg` and `libmagic` installed on the host (or run inside the
worker container, which has both). Generate the video test fixture once before running
video-related tests:
```bash
mkdir -p tests/fixtures
ffmpeg -y -f lavfi -i testsrc=duration=1:size=320x240:rate=5 -pix_fmt yuv420p tests/fixtures/sample.mp4
```

## API

`POST /api/v1/jobs` → returns a presigned S3 POST (size/type-enforced by S3 itself, not
just app-level checks) plus a `job_id`.
`POST /api/v1/jobs/{job_id}/confirm-upload` → idempotent; enqueues processing.
`GET /api/v1/jobs/{job_id}` → status, ownership-checked.
`GET /api/v1/health` / `GET /api/v1/ready` → liveness / dependency readiness.
`GET /metrics` → Prometheus exposition.

Every endpoint requires an `X-API-Key` header. Errors follow RFC 7807 (Problem Details)
uniformly — no ad hoc error shapes.

## What's actually been verified, not just written

This matters because a spec claiming a property and code actually having that property
are different things. Specifically proven by tests, not just asserted in comments:

- **Path traversal**: a client-supplied filename cannot influence the S3 storage key
  (`tests/security/test_path_traversal.py`).
- **Command injection**: FFmpeg is invoked with list arguments and `shell=False`; a
  malicious input string is passed through as one inert argument, never interpreted by a
  shell (`tests/security/test_ffmpeg_injection.py`).
- **SSRF**: FFmpeg's protocol whitelist genuinely blocks a real cloud-metadata-endpoint URL
  at runtime, not just in the argument list
  (`tests/integration/test_ffmpeg_pipeline_real.py::test_protocol_whitelist_blocks_network_input`).
- **IDOR**: cross-owner reads and cross-owner confirm-upload calls are both rejected
  (`tests/integration/test_job_lifecycle.py`).
- **File-type spoofing**: a real magic-byte check, not a trust-the-client-header check, using
  genuine test files (`tests/security/test_file_type_validation.py`).
- **Decompression bombs**: Pillow's own guard is wired up and actually fires
  (`tests/security/test_pillow_bomb_guard.py`).
- **Duplicate processing**: a distributed Redis lock genuinely prevents two workers from
  processing the same job (`tests/security/test_idempotency_locking.py`).
- **Moderation gating**: rejected/manual-review content is proven to never receive a
  publishable result URL (`tests/security/test_moderation_gate.py`).
- **Full lifecycle, both media types**: real presigned-POST S3 upload → confirm → Celery
  (eager) processing → completed status with CDN URL, for both image and video, including a
  real (non-mocked) FFmpeg transcode and thumbnail extraction
  (`tests/integration/test_job_lifecycle.py`, `tests/integration/test_ffmpeg_pipeline_real.py`).

## Bugs this build history actually caught (not hypothetical — found by running the code)

1. A stale job-status snapshot returned by `confirm-upload` under Celery's eager execution
   mode — invisible under a real async broker, but a real bug nonetheless. Fixed by
   re-fetching state after `.delay()` returns.
2. Short video clips failing their *entire* job because thumbnail extraction seeks past the
   clip's duration. Fixed with a t=0 fallback rather than treating the thumbnail as
   load-bearing.
3. FFmpeg exiting 0 while silently producing no output file (the root cause of #2). Fixed by
   checking output existence/size explicitly rather than trusting the exit code alone.
4. `Redis[str]` — a mypy-stub-only generic — crashing at import time in the installed
   redis-py version, because function-parameter-default type annotations are evaluated
   eagerly by the interpreter, unlike class-level or local-variable annotations. `mypy
   --strict` was satisfied the whole time; only actually importing the app caught it.
5. 26 real CVEs across Pillow, python-multipart, and starlette from the initial dependency
   pins, caught by `pip-audit` and fixed by version bumps, re-verified against the full test
   suite afterward.

## Project layout

See the module-by-module breakdown in the original build brief, or just read
`app/main.py` → `app/api/v1/jobs.py` → `app/tasks/image_tasks.py` in that order; that's
the real execution path for the core feature.
