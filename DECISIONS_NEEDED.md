# Decisions Required Before Production

Every item below was deliberately left unresolved in the codebase because it's a business,
legal, or infrastructure decision — not an engineering one. The code has a working default
or a stubbed interface for each, but "works" and "production-ready" are different claims.

## 1. Cloud account, region, and compute target
The app is fully containerized but nothing in this repo provisions real AWS infrastructure.
Decide: which AWS account, which region, ECS or EKS (not both — `infra/terraform/` in the
original spec was never built out precisely because this wasn't answered). Until this is
decided, the app only runs via `docker-compose` for local development, with `S3_ENDPOINT_URL`
pointed at a real S3-compatible endpoint or moto for testing.

## 2. Content moderation vendor
`app/services/moderation_service.py` has a working state machine (approved / rejected /
manual_review) fully wired into both the image and video task pipelines and covered by
tests — but the actual vendor call raises `NotImplementedError`. `MODERATION_PROVIDER=none`
(the current default) auto-approves everything, which is only acceptable for a non-UGC,
internal, or demo deployment. Before any real end-user uploads are processed:
- Choose a vendor (AWS Rekognition, Hive Moderation, or equivalent).
- Tune `MODERATION_CONFIDENCE_THRESHOLD` against real test content.
- Decide what happens to rejected content: hard delete, or retain under a legal hold policy.
- Implement `_scan_with_rekognition` / `_scan_with_hive` in that file — the interface and
  call sites are ready; only the vendor integration itself is missing.

## 3. API key storage and rotation
`app/auth.py` currently parses `VALID_API_KEYS` from a single comma-separated environment
variable. This works for a handful of keys but has no rotation, no revocation, and no
per-key rate-limit tiers. Before onboarding real external clients, replace `_parse_key_map`
with a database-backed key table (see the docstring in that function for the exact swap
point).

## 4. Structured log shipping
Logs are structured JSON to stdout (see `app/logging_config.py`) with API keys and
presigned-URL signatures redacted before emission — verified by
`tests/security/test_structured_log_redaction.py`-equivalent coverage in the moderation and
lifecycle tests. Where those logs go in production (CloudWatch, ELK, Datadog, etc.) depends
entirely on the answer to item #1 and is not configured here.

## 5. Rejected/quarantined content retention policy
Related to #2: when moderation flags something as `manual_review`, the file sits in the raw
S3 bucket (which has a 24-hour lifecycle expiry) but there is no admin review tool in this
repo to act on it before that expiry. Either build that tool, extend the lifecycle rule for
quarantined items specifically, or accept that unreviewed borderline content silently expires
after 24 hours — pick one deliberately.

## 6. Deployment stage in CI
`.github/workflows/ci.yml` runs lint, strict type-check, tests with an 85% coverage floor,
dependency audit, and container image builds + Trivy scans on every PR. It deliberately stops
there — no `deploy` job exists, because it can't be written correctly without item #1.
